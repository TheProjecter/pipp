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
from pipp_utils import *


class PippProject(object):
    
    def __init__(self, in_root, full):

        #--
        # Parse the project definition
        #--
        self.in_root = in_root.rstrip('\\.') # TBD!!!!
        self.out_root = os.path.join(self.in_root, 'out')
        self.index = '/index.pip'
        self.stylesheet_fname = '/pipp.xsl'
        self.state_xml = os.path.join(in_root, 'pipp.xml')
        if not os.path.exists(self.state_xml):
            open(self.state_xml, 'w').write('<page src=""/>')
        self.orig_state = open(self.state_xml).read()

        #--
        # Create the DOM for the state document
        #--
        if full:
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

        #--
        # If state has changed, do a full rebuild
        #--
        new_state = open(self.state_xml).read()
        if new_state != self.orig_state:
            print "State has changed - initiating full rebuild"
            self.orig_state = new_state
            # TBD: can we do this without creating a new project instance?
            PippProject(self.in_root, True).build_full()

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
        state_node = self.state_doc.documentElement
        state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', self.index)
        PippFile(self, state_node).build(do_children=True)
        self.write_state()

    #--
    # Partial rebuild of a project. Check pages in state XML for modified files.
    #--
    def build(self):
        for state_node in self.state_doc.xpath('//page'):                
            PippFile(self, state_node).cond_build()
        self.write_state()

    #--
    # Serve a project with the built-in web server
    #--
    def serve(self, listen=('127.0.0.1', 8080)):
        if not os.path.exists(self.state_xml) or not os.path.exists(self.out_root):
            print "Project's first use - initiating full build"
            self.build_full()
            # TBD: this is a little hacky; refactor
            self.state_doc = NonvalidatingReader.parseUri(OsPathToUri(self.state_xml))
        os.chdir(self.out_root)

        self.node_map = {}
        for page in self.state_doc.xpath('//page'):                
            src = Conversions.StringValue(page.attributes[(EMPTY_NAMESPACE, 'src')])
            in_path = self.abs_in_path(src)
            out_path = re.sub('\.pip$', '.html', self.abs_out_path(in_path))        
            self.node_map[out_path[len(self.out_root):]] = page

        httpd = BaseHTTPServer.HTTPServer(listen, PippHTTPRequestHandler)
        httpd.pipp_project = self
        print "Serving project at http://127.0.0.1:8080/"
        httpd.serve_forever()


class PippFile(object):

    def __init__(self, project, state_node):
        self.project = project
        self.state_node = state_node
        self.file_name = state_node.getAttributeNS(EMPTY_NAMESPACE, 'src')
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
        for node in self.depends_node.childNodes:
            if file_name == get_text(node):
                return
        new_node = self.project.state_doc.createElementNS(EMPTY_NAMESPACE, 'depend')
        new_node.appendChild(self.project.state_doc.createTextNode(file_name))
        self.depends_node.appendChild(new_node)

    #--
    # Process a .pip file
    #--
    def build(self, do_children=False):

        #--
        # Create structural nodes in state document, to be filled during processing
        #--
        for node_name in ['exports', 'depends', 'children']:
            new_node = self.project.state_doc.createElementNS(EMPTY_NAMESPACE, node_name)
            self.state_node.appendChild(new_node)
            setattr(self, node_name + '_node', new_node)

        #--
        # Run the XSLT processor
        #--
        input = InputSource.DefaultFactory.fromUri(OsPathToUri(self.project.in_root + self.file_name))
        self.project.processor.extensionParams[(NAMESPACE, 'context')] = self
        output = self.project.processor.run(input)

        #--
        # Determine the output file name and write output to it
        #--
        abs_output_file = self.abs_out_path(self.abs_in_path(self.out_file))
        output_fh = open(abs_output_file, 'w')
        output_fh.write(output)
        output_fh.close()

        #--
        # Process all this file's children. If the child already has child nodes in
        # the state dom, it is a "child-file" and not processed.
        #--
        if do_children:
            for child in self.children_node.childNodes:
                if not child.hasChildNodes():
                    PippFile(self.project, child).build(do_children=True)

    #--
    # If any dependent files have a newer modification time than the target, rebuild
    #--
    def cond_build(self):    
        abs_output_file = self.abs_out_path(self.abs_in_path(self.out_file))
        build_time = os.stat(abs_output_file).st_mtime
        deps = [self.file_name] + [get_text(x) for x in self.state_node.xpath('depends/depend')]
        if any(os.stat(self.abs_in_path(d)).st_mtime > build_time for d in deps):

            new_state_node = self.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
            new_state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', self.file_name)
            self.state_node.parentNode.insertBefore(new_state_node, self.state_node)
            old_state_node = self.state_node
            self.state_node = new_state_node
            try:                
                self.build()
            except:
                old_state_node.parentNode.removeChild(new_state_node)
                self.state_node = old_state_node
                raise            

            #--
            # Merge new state data into the tree
            #--
            cn = new_state_node.xpath('children')[0]
            for x in list(cn.childNodes):
                cn.removeChild(x)
            pcn = old_state_node.xpath('children')[0]
            for x in list(pcn.childNodes):
                cn.appendChild(x)                
            new_state_node.parentNode.removeChild(old_state_node)
            return new_state_node


#--
# Run as a webserver that outputs the selected project, rebuilding output
# files on demand.
#--
class PippHTTPRequestHandler (SimpleHTTPServer.SimpleHTTPRequestHandler):
    def log_request(self, code, size=None):
        pass

    def do_GET(self):      
        try:
            if self.server.pipp_project.node_map.has_key(self.path):            
                state_node = PippFile(self.server.pipp_project, self.server.pipp_project.node_map[self.path]).cond_build()
                if state_node:
                    self.server.pipp_project.write_state()
                    self.server.pipp_project.node_map[self.path] = state_node
            SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)
        except:
            self.send_response(500)
            self.send_header("Content-type", 'text/plain')
            self.end_headers()
            self.wfile.write(traceback.format_exc())

    
#--
# Main entry point - parse the command line
#--
if len(sys.argv) == 2:
    in_root = os.path.join(os.getcwd(), sys.argv[1])
    PippProject(in_root, False).build()
elif len(sys.argv) == 3 and sys.argv[1] == '-f':
    in_root = os.path.join(os.getcwd(), sys.argv[2])
    PippProject(in_root, True).build_full()
elif len(sys.argv) == 3 and sys.argv[1] == '-s':
    in_root = os.path.join(os.getcwd(), sys.argv[2])
    PippProject(in_root, False).serve()


#--
# Otherwise the command line is invalid - display usage information
#--
else:
    print """
Pipp - Python Internet Pre-Processor
Copyright 2004-2007 Paul Johnston, distributed under the BSD license

Usage: %s [-f] [-s] [path]

For full details, please read the documentation.
""" % (sys.argv[0], sys.argv[0])
