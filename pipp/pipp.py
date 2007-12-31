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
import re, os, sys, BaseHTTPServer, SimpleHTTPServer, traceback
from optparse import OptionParser
from pipp_utils import *
import pipp_xslt


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
            self.state_doc = NonvalidatingReader.parseString('<page/>', 'abc')
        else:
            self.state_doc = NonvalidatingReader.parseUri(OsPathToUri(self.state_xml))

        #--
        # Create the XSLT processor
        #--
        self.processor = Processor.Processor(stylesheetAltUris = [OsPathToUri(pipp_dir + os.path.sep)])
        self.processor.registerExtensionModules(['pipp_xslt'])
        stylesheet = InputSource.DefaultFactory.fromUri(OsPathToUri(self.in_root + self.stylesheet_fname))
        self.processor.appendStylesheet(stylesheet)

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


#--
# Run as a webserver that outputs the selected project, rebuilding output
# files on demand.
#--
class PippHTTPRequestHandler (SimpleHTTPServer.SimpleHTTPRequestHandler):
    def log_request(self, code, size=None):
        pass

    def do_GET(self):      
        try:
            if self.path.endswith('/'):
                self.path += '.html'
            if self.path.endswith('.html'):
                path = re.sub('.html$', '.pip', self.path)
                nodes = self.server.pipp_project.state_doc.xpath("//page[@src='%s']" % path.replace("'", ""))
                if nodes:
                    if PippFile(self.server.pipp_project, nodes[0]).build(force=False):
                        self.server.pipp_project.write_state()
                        # Reset caches inside pipp_xslt
                        pipp_xslt.images = {}
                        pipp_xslt.processors = {}
                        pipp_xslt.files = {}                        
            SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
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

        #--
        # Determine if the timestamp on any dependencies is newer than the output
        #--
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

        #--
        # Prepare the new state node
        #--
        self.state_node = self.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
        self.state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', self.file_name)        
        for node_name in ['exports', 'depends', 'edepends', 'children']:
            new_node = self.project.state_doc.createElementNS(EMPTY_NAMESPACE, node_name)
            self.state_node.appendChild(new_node)
            setattr(self, node_name + '_node', new_node)

        #--
        # Run the XSLT processor
        #--
        self.old_state_node.parentNode.insertBefore(self.state_node, self.old_state_node)
        self.old_state_node.parentNode.removeChild(self.old_state_node)
        try:
            input = InputSource.DefaultFactory.fromUri(OsPathToUri(self.project.in_root + self.file_name))
            self.project.processor.extensionParams[(NAMESPACE, 'context')] = self
            output = self.project.processor.run(input)
        except:
            self.state_node.parentNode.insertBefore(self.old_state_node, self.state_node)
            self.state_node.parentNode.removeChild(self.state_node)
            raise

        #--
        # Determine the output file name and write output to it
        #--
        abs_output_file = self.abs_out_path(self.abs_in_path(self.out_file))
        output_fh = open(abs_output_file, 'w')
        output_fh.write(output)
        output_fh.close()

        #--
        # Determine if any exported state was changed
        #--
        old_exports = dict((x.tagName, get_text(x)) for x in self.old_state_node.xpath('exports/*'))
        new_exports = dict((x.tagName, get_text(x)) for x in self.state_node.xpath('exports/*'))                    
        changed = []
        for e in new_exports:
            if new_exports[e] != old_exports.pop(e, None):
                changed.append(e)
        changed += old_exports.keys()        
        self.project.changed_exports += ['%s:%s' % (self.file_name, c) for c in changed]        

        #--
        # Determine if the list of children changed
        #--
        old_children = [Conversions.StringValue(x) for x in self.old_state_node.xpath('children/page/@src')]
        new_children = [Conversions.StringValue(x) for x in self.state_node.xpath('children/page/@src')]
        if old_children != new_children:
            self.project.changed_exports.append('%s:children' % self.file_name)

        #--
        # Build children as appropriate
        #--        
        children_map = dict((x.getAttributeNS(EMPTY_NAMESPACE, 'src'), x) for x in self.old_state_node.xpath('children/page'))
        for skel_node in list(self.state_node.xpath('children/page')):
            file_name = skel_node.getAttributeNS(EMPTY_NAMESPACE, 'src')
            full_node = children_map.get(file_name)
            isnew = not bool(full_node)
            if isnew:
                full_node = self.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
                full_node.setAttributeNS(EMPTY_NAMESPACE, 'src', file_name)
            skel_node.parentNode.insertBefore(full_node, skel_node)
            skel_node.parentNode.removeChild(skel_node)
            if (isnew or force_children) and file_name.endswith('.pip'):
                PippFile(self.project, full_node).build(force or isnew, force_children)
            
        return True


#--
# Main entry point - parse the command line
#--
parser = OptionParser(usage="usage: %prog [options] project_root")
parser.add_option("-s", "--serve", dest="serve", action='store_true',
        help='Start a web server that serves the project; this is useful for development')
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
