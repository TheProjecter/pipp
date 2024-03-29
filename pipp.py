#!/usr/bin/python
#--
# Pipp main module. This parses the command line and starts the XSLT processor.
# It also handles project files and the state XML.
#--
from Ft.Xml.Xslt import Processor
from Ft.Xml import InputSource, EMPTY_NAMESPACE
from Ft.Xml.Domlette import NonvalidatingReader
from Ft.Xml.Lib.Print import PrettyPrint
from Ft.Lib.Uri import OsPathToUri
from Ft.Xml.XPath import Compile, Conversions
import re, os, sys, BaseHTTPServer, SimpleHTTPServer, traceback, threading
import urllib2 as ul
from optparse import OptionParser
from pipp_utils import *
import pipp_xslt

threads = 10 # for checking external links

dtd_defs = {
    'strict': '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01//EN" "http://www.w3.org/TR/html4/strict.dtd">',
    'transitional': '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.01 Transitional//EN" "http://www.w3.org/TR/html4/loose.dtd">',
    'frameset': '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 4.01 Frameset//EN" "http://www.w3.org/TR/html4/frameset.dtd">',
}

class SpellingMistake(Exception):
    def __init__(self, msg, filename, words):
        super(SpellingMistake, self).__init__(msg)
        self.filename = filename
        self.words = words


class PippProject(object):

    def __init__(self, in_root, options):

        #--
        # Parse the project definition
        #--
        self.options = options
        self.in_root = in_root.rstrip('/\\')
        self.out_root = os.path.join(self.in_root, 'out')
        self.index = '/index.pip'
        self.stylesheet_fname = '/pipp.xsl'
        self.state_xml = os.path.join(in_root, 'pipp.xml')
        self.changed_exports = []
        self.new_project = not os.path.exists(self.state_xml)
        if self.new_project:
            open(self.state_xml, 'w').write('<page src="%s"><exports><link>%s</link></exports></page>'
                    % (self.index, re.sub('.pip$', '.html', self.index)))
        self.state_doc = NonvalidatingReader.parseUri(OsPathToUri(self.state_xml))
        self._processor = None

    #--
    # Create the XSLT processor
    #--
    @property
    def processor(self):
        if not self._processor:
            _processor = Processor.Processor(stylesheetAltUris = [OsPathToUri(pipp_dir + os.path.sep)])
            _processor.registerExtensionModules(['pipp_xslt'])
            stylesheet = InputSource.DefaultFactory.fromUri(OsPathToUri(self.in_root + self.stylesheet_fname))
            _processor.appendStylesheet(stylesheet)
            self._processor = _processor
        return self._processor

    #--
    # Write the state DOM over the previous state XML
    #--
    def write_state(self):
        state_file = open(self.state_xml, 'w')
        PrettyPrint(self.state_doc.documentElement, state_file)
        state_file.close()

        if self.changed_exports:
            rebuild_pages = set()
            for ch in self.changed_exports:
                nodes = self.state_doc.xpath("//page[edepends/depend[text() = '%s']]" % ch.replace("'", ""))
                rebuild_pages = rebuild_pages.union(nodes)
            for page in rebuild_pages:
                PippFile(self, page).build(force=True, force_children=False)
            self.changed_exports = []

    #--
    # Given an absolute input path, return the absolute output path. If the output
    # directories do not exist then this function will create them.
    #--
    def abs_out_path(self, in_path):
        abs_output_file = self.out_root + in_path[len(self.in_root):]
        if not os.path.isdir(os.path.dirname(abs_output_file)):
            os.makedirs(os.path.dirname(abs_output_file))
        return abs_output_file

    def abs_in_path(self, file_name):
        if file_name[0] == '/':
            return self.in_root + file_name
        else:
            raise Exception('Error: abs_in_path called on project with relative path')

    #--
    # Full build of a project. Process the index page and recurse.
    #--
    def build_full(self):
        self.changed_exports = []
        state_node = self.state_doc.documentElement
        state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', self.index)
        PippFile(self, state_node).build(force=True, force_children=True)
        self.write_state()

    #--
    # Partial rebuild of a project. Check pages in state XML for modified files.
    #--
    def build(self):
        for state_node in self.state_doc.xpath('//page'):
            PippFile(self, state_node).build()
        self.write_state()

    #--
    # Serve a project with the built-in web server
    #--
    def serve(self, listen):
        os.chdir(self.out_root)
        httpd = BaseHTTPServer.HTTPServer(listen, PippHTTPRequestHandler)
        httpd.pipp_project = self
        print "Serving project at http://%s:%d/" % listen
        httpd.serve_forever()

    def get_state_node(self, path):
        nodes = self.state_doc.xpath("//page[@src='%s']" % path.replace("'", ""))
        return nodes and nodes[0] or None


    def check_links(self):
        elink = {}
        for node in self.state_doc.xpath("//page"):
            src = get_text(node.xpath("exports/link")[0])
            for link in node.xpath("links/link"):
                link = get_text(link)
                anchor = None
                if '#' in link:
                    link, anchor = link.split('#')
                    if not link:
                        continue # TBD: check anchor
                if "\\" in link:
                    print "In %s, link contains backslash: %s" % (src, link)
                    continue
                if link.startswith("/"):
                    print "In %s, link starts with a slash: %s" % (src, link)
                    continue
                if any(link.startswith(x) for x in ('http:', 'https:', 'ftp:', 'mailto:')):
                    elink.setdefault(link, []).append(src)
                else:
                    target = os.path.join(self.out_root, src[1:])
                    target = os.path.join(os.path.dirname(target), link)
                    try:
                        content = open(target).read()
                    except IOError, e:
                        print "In %s, link target missing: %s" % (src, link)
                    if anchor and (u'name="%s"' % anchor) not in content:
                        print "In %s, link anchor missing: %s" % (src, link)
        return elink

    def check_elinks(self, elinks):
        thrd = []
        for i in range(threads):
            t = LinkChecker()
            t.elinks = elinks
            thrd.append(t)
            t.start()
        for t in thrd:
            t.join()


errors = []

class LinkChecker(threading.Thread):
    def run(self):
        while True:
            try:
                l,s = self.elinks.popitem()
            except KeyError:
                return
            if l.startswith('mailto:'):
                continue
            try:
                conn = ul.urlopen(l)
                content = conn.read()
            except ul.URLError, e:
                print "Bad link: %s (%s)" % (l, str(e)) # (l, e.reason.args[1])
                print s
                continue
            if conn.geturl() != l:
                print "Redirect: %s %s" % (conn.geturl(), l)
                print s


#--
# Run as a webserver that outputs the selected project, rebuilding output
# files on demand.
#--
class PippHTTPRequestHandler (SimpleHTTPServer.SimpleHTTPRequestHandler):
    def log_request(self, code, size=None):
        pass

    def log_error(self, format, *args):
        if args and args[0] == 404 and self.path == '/favicon.ico':
            return
        format += ', path ' + self.path
        self.log_message(format, *args)

    def do_POST(self):
        if self.path == '/__addwords':
            clen = int(self.headers.get('Content-Length', 0))
            data = clen and self.rfile.read(clen)
            words = [elem[8:] for elem in data.split('&') if elem.startswith('addword=')]
            wl = open(self.server.pipp_project.in_root + '/en.pws', 'a')
            wl.write('\n'.join(words) + '\n')
            wl.close()
            if self.headers.get('Referer'):
                self.send_response(301)
                self.send_header("Location", self.headers['Referer'])
                self.end_headers()
        else:
            self.send_error(404, "File not found")

    def do_GET(self):
        project = self.server.pipp_project
        try:
            if self.path.endswith('/'):
                self.path += 'index.html'
            if self.path.endswith('.html'):
                node = project.get_state_node(re.sub('.html$', '.pip', self.path))
                if node:
                    checked = {}
                    any_built = False
                    for n in node.xpath('edepends/depend'):
                        fname = get_text(n).split(':')[0]
                        if not checked.has_key(fname):
                            abs_in = project.abs_in_path(fname)
                            abs_out = re.sub('.pip$', '.html', project.abs_out_path(abs_in))
                            if (os.path.exists(abs_in) and
                                (not os.path.exists(abs_out) or
                                    os.stat(abs_in).st_mtime > os.stat(abs_out).st_mtime)):
                                PippFile(project, project.get_state_node(fname)).build(force=True)
                                any_built = True
                            checked[fname] = 1
                    any_built = any_built or PippFile(project, node).build(force=False)
                    if any_built:
                        project.write_state()
                        # Avoid any state being stored between requests
                        pipp_xslt.images = {}
                        pipp_xslt.processors = {}
                        pipp_xslt.files = {}
                        project._processor = None
            SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
        except SpellingMistake, e:
            self.send_response(500)
            self.send_header("Content-type", 'text/html')
            self.end_headers()
            self.wfile.write("File '%s' contains misspelled words:<form action=\"/__addwords\" method=\"post\">" % e.filename)
            for word in set(e.words):
                if word:
                    self.wfile.write('<input type="checkbox" name="addword" value="%s"/>%s<br/>' % (word, word))
            self.wfile.write('<input type="submit"/></form>')
        except:
            self.send_response(500)
            self.send_header("Content-type", 'text/plain')
            self.end_headers()
            self.wfile.write(traceback.format_exc())


class PippFile(object):

    def __init__(self, project, old_state_node):
        self.project = project
        self.old_state_node = old_state_node
        self.file_name = old_state_node.getAttributeNS(EMPTY_NAMESPACE, 'src')
        self.out_file = re.sub('\.pip$', '.html', self.file_name)

    @property
    def in_root(self):
        return self.project.in_root

    @property
    def out_root(self):
        return self.project.out_root

    @property
    def state_doc(self):
        return self.project.state_doc

    @property
    def state_xml(self):
        return self.project.state_xml

    #--
    # Given a pipp path, return the absolute path in the input tree. If the path
    # is relative, it is relative to the current file. If it is absolute then the
    # in-root is prepended.
    #--
    def abs_in_path(self, file_name):
        if file_name[0] == '/':
            return self.project.in_root + file_name
        else:
            return os.path.dirname(self.project.in_root + self.file_name) + '/' + file_name

    def abs_out_path(self, path):
        return self.project.abs_out_path(path)

    #--
    # Add a dependency
    #--
    def add_depends(self, file_name):
        if file_name == self.file_name:
            return
        for node in self.depends_node.childNodes:
            if file_name == get_text(node):
                return
        new_node = self.project.state_doc.createElementNS(EMPTY_NAMESPACE, 'depend')
        new_node.appendChild(self.project.state_doc.createTextNode(file_name))
        self.depends_node.appendChild(new_node)

    def add_edepends(self, file_name, export):
        # TBD: reintroduce this once map-view works off in-memory state xml
        #if file_name == self.file_name:
        #    return
        comb = file_name + ':' + export
        if self.edepends_node.xpath("depend[text() = '%s']" % comb.replace("'", "")):
            return
        new_node = self.project.state_doc.createElementNS(EMPTY_NAMESPACE, 'depend')
        new_node.appendChild(self.project.state_doc.createTextNode(comb))
        self.edepends_node.appendChild(new_node)

    #--
    # Process a .pip file. Returns true/false depending on whether the file was
    # actually processed. Recursively processes any new children, and if desired,
    # any existing children as well.
    #--
    def build(self, force=False, force_children=False):

        # Determine if the timestamp on any dependencies is newer than the output
        if not force:
            abs_output_file = self.abs_out_path(self.abs_in_path(self.out_file))
            if os.path.exists(abs_output_file):
                build_time = os.stat(abs_output_file).st_mtime
                deps = [self.file_name] + [get_text(x) for x in self.old_state_node.xpath('depends/depend')]
                changed = any(os.stat(self.abs_in_path(d)).st_mtime > build_time for d in deps)
                if not changed:
                    return False

        if self.project.options.verbose:
            print "Building " + self.file_name

        # Prepare the new state node
        self.state_node = self.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
        self.state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', self.file_name)
        for node_name in ['exports', 'links', 'produces', 'depends', 'edepends', 'children']:
            new_node = self.project.state_doc.createElementNS(EMPTY_NAMESPACE, node_name)
            self.state_node.appendChild(new_node)
            setattr(self, node_name + '_node', new_node)
        self.add_depends(self.project.stylesheet_fname)

        # Run the XSLT processor
        self.old_state_node.parentNode.insertBefore(self.state_node, self.old_state_node)
        self.old_state_node.parentNode.removeChild(self.old_state_node)
        try:
            input = InputSource.DefaultFactory.fromUri(OsPathToUri(self.project.in_root + self.file_name))
            self.project.processor.extensionParams[(NAMESPACE, 'context')] = self
            output = self.project.processor.run(input)

            # Spell checking currently disabled
            if 0: # not self.state_node.xpath('exports/spell'):
                # Check spelling
                pin, pout = os.popen4('"c:/program files/aspell/bin/aspell" --master=british --home-dir=%s --mode=sgml --rem-sgml-check=alt list' % self.in_root)
                try:
                    pin.write(output)
                except IOError:
                    raise Exception('aspell failed: ' + pout.read())
                pin.close()
                bad_words = pout.read()
                pout.close()
                if bad_words:
                    raise SpellingMistake("Mispelled words in '%s': %s" % (self.out_file, bad_words), self.out_file, bad_words.split('\n'))

        except:
            self.state_node.parentNode.insertBefore(self.old_state_node, self.state_node)
            self.state_node.parentNode.removeChild(self.state_node)
            raise

        # Determine the output file name and write output to it
        abs_output_file = self.abs_out_path(self.abs_in_path(self.out_file))

        dtdnode = self.state_node.xpath('exports/dtd')
        dtd = dtdnode and Conversions.StringValue(dtdnode[0]) or 'strict'
        output_fh = open(abs_output_file, 'w')
        output_fh.write(dtd_defs[dtd] + '\n' + output)
        output_fh.close()

        # Determine if any exported state was changed
        old_exports = dict((x.tagName, get_text(x)) for x in self.old_state_node.xpath('exports/*'))
        new_exports = dict((x.tagName, get_text(x)) for x in self.state_node.xpath('exports/*'))
        changed = []
        for e in new_exports:
            if new_exports[e] != old_exports.pop(e, None):
                changed.append(e)
        changed += old_exports.keys()
        self.project.changed_exports += ['%s:%s' % (self.file_name, c) for c in changed]

        # Determine if the list of children changed
        old_children = [Conversions.StringValue(x) for x in self.old_state_node.xpath('children/page/@src')]
        new_children = [Conversions.StringValue(x) for x in self.state_node.xpath('children/page/@src')]
        if old_children != new_children:
            self.project.changed_exports.append('%s:children' % self.file_name)

        # Build children as appropriate
        children_map = dict((x.getAttributeNS(EMPTY_NAMESPACE, 'src'), x) for x in self.old_state_node.xpath('children/page'))
        for skel_node in list(self.state_node.xpath('children/page')):
            file_name = skel_node.getAttributeNS(EMPTY_NAMESPACE, 'src')
            full_node = children_map.get(file_name)
            isnew = not bool(full_node)
            if isnew:
                full_node = skel_node
            else:
                skel_node.parentNode.insertBefore(full_node, skel_node)
                skel_node.parentNode.removeChild(skel_node)
            if (isnew or force_children) and file_name.endswith('.pip'):
                PippFile(self.project, full_node).build(force or isnew, force_children)

        return True


#--
# Main entry point - parse the command line
#--
if __name__ == '__main__':
    parser = OptionParser(usage="usage: %prog [options] project_root")
    parser.add_option("-s", "--serve", dest="serve", action='store_true',
            help='Start a web server that serves the project; this is useful for development')
    parser.add_option("-c", "--check-links", dest="check_links", action='store_true',
            help='Check links in the site')
    parser.add_option("-e", "--ext-links", dest="ext_links", action='store_true',
            help='Display external links')
    parser.add_option("-p", "--port", dest="port", type='int', default=8080,
            help='Specify port for the web server (default %default)')
    parser.add_option("-l", "--listen", dest="listen", default='127.0.0.1',
            help='Specify the listening address for the web server (default %default)')
    parser.add_option("-f", "--full", dest="full", action='store_true',
            help='Initiate a full rebuild of the project')
    parser.add_option("-v", "--verbose", dest="verbose", action='store_true',
            help='Produce more verbose output')

    (options, args) = parser.parse_args()
    if len(args) != 1:
        parser.print_help()
    else:
        if args[0] == '.':
            in_root = os.getcwd()
        else:
            in_root = os.path.join(os.getcwd(), args[0])
        prj = PippProject(in_root, options)
        if options.full:
            prj.build_full()
        elif prj.new_project:
            print "Project's first use - initiating full build"
            prj.build_full()
        if options.serve:
            prj.serve(listen=(options.listen, options.port))
        if not options.full and not options.serve:
            prj.build()
        if options.check_links or options.ext_links:
            elinks = prj.check_links()
            if options.ext_links:
                prj.check_elinks(elinks)
                #for e in elinks:
                #    print e
