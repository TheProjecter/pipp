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
from pipp_utils import *
import re, os, sys

class PippContext(object):
    
    def __init__(self, in_root, out_root, state_xml, state_doc):
        self.in_root = in_root
        self.out_root = out_root
        self.state_xml = state_xml
        self.state_doc = state_doc


#--
# Build a project - read the project file and run the XSLT processor on the
# index page.
#--
def build_project(project, full=False):

    #--
    # Parse the project definition
    #--
    project_doc = NonvalidatingReader.parseUri(OsPathToUri(project))
    in_root = project_doc.xpath('string(/project/in-root)')
    out_root = project_doc.xpath('string(/project/out-root)')
    index = project_doc.xpath('string(/project/index)')
    stylesheet_fname = project_doc.xpath('string(/project/stylesheet)')
    state_xml = project_doc.xpath('string(/project/state)')

    #--
    # Create the DOM for the state document
    # TBD: make this the same for full/partial
    #--
    if full:
        state_doc = NonvalidatingReader.parseString('<page/>', 'abc')
    else:
        state_doc = NonvalidatingReader.parseUri(OsPathToUri(state_xml))
    
    #--
    # Create the XSLT processor
    #--
    processor = Processor.Processor(stylesheetAltUris = [OsPathToUri(pipp_dir + os.path.sep)])
    processor.registerExtensionModules(['pipp_xslt'])
    stylesheet = InputSource.DefaultFactory.fromUri(OsPathToUri(in_root + stylesheet_fname))
    processor.appendStylesheet(stylesheet)

    ctx = PippContext(in_root, out_root, state_xml, state_doc)
    processor.extensionParams[(NAMESPACE, 'context')] = ctx

    #--
    # Process the index file. This will recursively process all its children.
    #--
    if full:
        state_node = state_doc.documentElement
        state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', index)
        ctx.read_state_node = state_node
        build_file(processor, state_node, do_children=True)

    #--
    # Go through all pages in state xml
    #--
    else:
        for page in state_doc.xpath('//page'):                
            src = Conversions.StringValue(page.attributes[(EMPTY_NAMESPACE, 'src')])
            in_path = abs_in_path(ctx, src)
            out_path = re.sub('\.pip$', '.html', abs_out_path(ctx, in_path))        
            build_time = os.stat(out_path).st_mtime

            deps = [src] + [get_text(x) for x in page.xpath('depends/depend')]
            if any(os.stat(abs_in_path(ctx, d)).st_mtime > build_time for d in deps):

                #--
                # If any dependent files have a newer modification time than the target, rebuild
                #--
                ctx.read_state_node = page
                state_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
                state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', src)
                build_file(processor, state_node)

    #--
    # Write the state DOM over the previous state XML
    #--
    state_file = open(state_xml, 'w')
    PrettyPrint(state_doc.documentElement, state_file)
    state_file.close()


#--
# Process a .pip file, and recursively process all its children.
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
        print 'Error: exception occured while processing %s:\n%s' % (ctr.file_name, e)
        sys.exit(1)

    #--
    # Determine the output file name and write output to it
    #--
    abs_output_file = abs_out_path(ctx, abs_in_path(ctx, ctx.out_file))
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
    build_project(project_fname, full=True)

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
