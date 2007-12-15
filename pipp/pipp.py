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
import re, os, sys, BaseHTTPServer, SimpleHTTPServer
from pipp_utils import *

#--
# Class to hold Pipp processing state
#--
class PippContext(object):
    
    def __init__(self, project, full):

        #--
        # Parse the project definition
        #--
        self.project = project
        self.project_doc = NonvalidatingReader.parseUri(OsPathToUri(project))
        self.in_root = self.project_doc.xpath('string(/project/in-root)')
        self.out_root = self.project_doc.xpath('string(/project/out-root)')
        self.index = self.project_doc.xpath('string(/project/index)')
        self.stylesheet_fname = self.project_doc.xpath('string(/project/stylesheet)')
        self.state_xml = self.project_doc.xpath('string(/project/state)')
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
    def create_processor(self):
        processor = Processor.Processor(stylesheetAltUris = [OsPathToUri(pipp_dir + os.path.sep)])
        processor.registerExtensionModules(['pipp_xslt'])
        stylesheet = InputSource.DefaultFactory.fromUri(OsPathToUri(self.in_root + self.stylesheet_fname))
        processor.appendStylesheet(stylesheet)
        processor.extensionParams[(NAMESPACE, 'context')] = self
        return processor

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
        if open(self.state_xml).read() != self.orig_state:
            build_project_full(self.project)

    #--
    # Given a pipp path, return the absolute path in the input tree. If the path
    # is relative, it is relative to the current file. If it is absolute then the
    # in-root is prepended.
    #--
    def abs_in_path(self, file_name):
        if file_name[0] == '/':
            return self.in_root + file_name
        else:
            return os.path.dirname(self.in_root + self.file_name) + '/' + file_name

    #--
    # Given an absolute input path, return the absolute output path. If the output
    # directories do not exist then this function will create them.
    #--
    def abs_out_path(self, in_path):
        abs_output_file = self.out_root + in_path[len(self.in_root):]
        if not os.path.isdir(os.path.dirname(abs_output_file)):
            os.makedirs(os.path.dirname(abs_output_file))
        return abs_output_file

    #--
    # Add a dependency
    #--
    def add_depends(self, file_name):
        for node in self.depends_node.childNodes:
            if file_name == get_text(node):
                return
        new_node = self.state_doc.createElementNS(EMPTY_NAMESPACE, 'depend')
        new_node.appendChild(self.state_doc.createTextNode(file_name))
        self.depends_node.appendChild(new_node)


#--
# Full build of a project. Process the index page and recurse.
#--
def build_project_full(project):
    ctx = PippContext(project, True)
    processor = ctx.create_processor()    
    state_node = ctx.state_doc.documentElement
    state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', ctx.index)
    build_file(processor, state_node, do_children=True)
    ctx.write_state()

#--
# Partial rebuild of a project. Check pages in state XML for modified files.
#--
def build_project(project):
    ctx = PippContext(project, False)
    processor = ctx.create_processor()    

    for page in ctx.state_doc.xpath('//page'):                
        src = Conversions.StringValue(page.attributes[(EMPTY_NAMESPACE, 'src')])
        in_path = ctx.abs_in_path(src)
        out_path = re.sub('\.pip$', '.html', ctx.abs_out_path(in_path))        
        cond_build_file(ctx, page, out_path, processor)

    ctx.write_state()

#--
# Run as a webserver that outputs the selected project, rebuilding output
# files on demand.
#--
class PippHTTPRequestHandler (SimpleHTTPServer.SimpleHTTPRequestHandler):
    def do_GET(self):      
        if self.server.node_map.has_key(self.path):
            state_node = cond_build_file(self.server.ctx, self.server.node_map[self.path], self.server.ctx.out_root + self.path, self.server.processor)
            if state_node:
                self.server.ctx.write_state()
                self.server.node_map[self.path] = state_node
        SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

def serve_project(project):
    ctx = PippContext(project, False)
    os.chdir(ctx.out_root)
    
    node_map = {}
    for page in ctx.state_doc.xpath('//page'):                
        src = Conversions.StringValue(page.attributes[(EMPTY_NAMESPACE, 'src')])
        in_path = ctx.abs_in_path(src)
        out_path = re.sub('\.pip$', '.html', ctx.abs_out_path(in_path))        
        node_map[out_path[len(ctx.out_root):]] = page
    
    httpd = BaseHTTPServer.HTTPServer(('127.0.0.1', 8080), PippHTTPRequestHandler)
    httpd.ctx = ctx
    httpd.processor = ctx.create_processor()
    httpd.node_map = node_map
    httpd.serve_forever()


#--
# If any dependent files have a newer modification time than the target, rebuild
#--
def cond_build_file(ctx, page, out_path, processor):
    build_time = os.stat(out_path).st_mtime
    src = Conversions.StringValue(page.attributes[(EMPTY_NAMESPACE, 'src')])
    deps = [src] + [get_text(x) for x in page.xpath('depends/depend')]
    if any(os.stat(ctx.abs_in_path(d)).st_mtime > build_time for d in deps):

        state_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
        state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', src)
        page.parentNode.insertBefore(state_node, page)
        build_file(processor, state_node)

        #--
        # Merge new state data into the tree
        #--
        cn = state_node.xpath('children')[0]
        for x in list(cn.childNodes):
            cn.removeChild(x)
        pcn = page.xpath('children')[0]
        for x in list(pcn.childNodes):
            cn.appendChild(x)                
        page.parentNode.removeChild(page)
        return state_node


#--
# Process a .pip file
#--
def build_file(processor, state_node, do_children=False):
    ctx = processor.extensionParams[(NAMESPACE, 'context')]

    #--
    # Locate the input file and read it
    #--
    ctx.file_name = state_node.getAttributeNS(EMPTY_NAMESPACE, 'src')
    input = InputSource.DefaultFactory.fromUri(OsPathToUri(ctx.in_root + ctx.file_name))
    ctx.out_file = re.sub('\.pip$', '.html', ctx.file_name)
    ctx.state_node = state_node

    #--
    # Create structural nodes in state document, to be filled during processing
    #--
    for node_name in ['exports', 'depends', 'children']:
        new_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, node_name)
        state_node.appendChild(new_node)
        setattr(ctx, node_name + '_node', new_node)

    #--
    # Run the XSLT processor
    #--
    try:
        output = processor.run(input)
    except Exception, e:
        print 'Error: exception occured while processing %s:\n%s' % (ctx.file_name, e)
        sys.exit(1)

    #--
    # Determine the output file name and write output to it
    #--
    abs_output_file = ctx.abs_out_path(ctx.abs_in_path(ctx.out_file))
    output_fh = open(abs_output_file, 'w')
    output_fh.write(output)
    output_fh.close()

    #--
    # Process all this file's children. If the child already has child nodes in
    # the state dom, it is a "child-file" and not processed.
    #--
    if do_children:
        for child in ctx.children_node.childNodes:
            if not child.hasChildNodes():
                ctx.read_state_node = child
                build_file(processor, child, do_children=True)
      
    
#--
# Main entry point - parse the command line
#--

#--
# If -c is specified, create the project file and an initial empty state file
#--
if len(sys.argv) == 7 and sys.argv[1] == '-c':
    (project, in_root, stylesheet, index, out_root) = sys.argv[2:]

    #--
    # Sanitise input
    #--
    if in_root[-1:] == '/': in_root = in_root[:-1]
    if out_root[-1:] == '/': out_root = out_root[:-1]
    if index[0:1] != '/': index = '/' + index
    if stylesheet[0:1] != '/': stylesheet = '/' + stylesheet
    state_fname = os.path.join(project_dir, '%s-state.xml' % project)

    #--
    # Check the project doesn't already exist
    #--
    project_fname = os.path.join(project_dir, '%s.xml' % project)
    if os.path.exists(project_fname):
        print 'Error: Project already exists'
        sys.exit(1)

    #--
    # Create the project file and empty state XML
    #--
    project_file = open(project_fname, 'w')
    project_file.write("""<project>
    <in-root>%s</in-root>
    <stylesheet>%s</stylesheet>
    <index>%s</index>
    <out-root>%s</out-root>
    <state>%s</state>
</project>""" % (in_root, stylesheet, index, out_root, state_fname))
    project_file.close()

    state_file = open(state_fname, 'w')
    state_file.write("<page/>")
    state_file.close()

    #--
    # Build the project
    #--
    build_project(project_fname)

#--
# If just a project name is specified, build it
#--
elif len(sys.argv) == 2:
    project_fname = '%s/%s.xml' % (project_dir, sys.argv[1])
    build_project(project_fname)
elif len(sys.argv) == 3 and sys.argv[1] == '-f':
    project_fname = '%s/%s.xml' % (project_dir, sys.argv[2])
    build_project_full(project_fname)
elif len(sys.argv) == 3 and sys.argv[1] == '-s':
    project_fname = '%s/%s.xml' % (project_dir, sys.argv[2])
    serve_project(project_fname)


#--
# Otherwise the command line is invalid - display usage information
#--
else:
    print """
Pipp - Python Internet Pre-Processor
Copyright 2004-2007 Paul Johnston, distributed under the BSD license

Initial usage: %s -c <project> <in-root> <stylesheet> <index> <out-root>
Further usage: %s <project>

For full details, please read the documentation.
""" % (sys.argv[0], sys.argv[0])
