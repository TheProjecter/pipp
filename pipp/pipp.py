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

#--
# Build a project - read the project file and run the XSLT processor on the
# index page.
#--
def build_project(project):

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
    #--
    state_doc = NonvalidatingReader.parseString('<page/>', 'abc')

    #--
    # Create the XSLT processor
    #--
    processor = Processor.Processor(stylesheetAltUris = [OsPathToUri(pipp_dir + os.path.sep)])
    processor.registerExtensionModules(['pipp_xslt'])
    stylesheet = InputSource.DefaultFactory.fromUri(OsPathToUri(in_root + stylesheet_fname))
    processor.appendStylesheet(stylesheet)

    processor.extensionParams[(NAMESPACE, 'in_root')] = in_root
    processor.extensionParams[(NAMESPACE, 'out_root')] = out_root
    processor.extensionParams[(NAMESPACE, 'state_xml')] = state_xml
    processor.extensionParams[(NAMESPACE, 'state_doc')] = state_doc

    #--
    # Process the index file. This will recursively process all its children.
    #--
    state_node = state_doc.documentElement
    state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', index)
    processor.extensionParams[(NAMESPACE, 'read_state_node')] = state_node
    build_file(processor, state_node, do_children=True)

    #--
    # Write the state DOM over the previous state XML
    #--
    state_file = open(state_xml, 'w')
    PrettyPrint(state_doc.documentElement, state_file)
    state_file.close()

#--
# Build a project - read the project file and run the XSLT processor on the
# index page.
#--
def rebuild_project(project):

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
    #--
    state_doc = NonvalidatingReader.parseUri(OsPathToUri(state_xml))

    #--
    # Create the XSLT processor
    #--
    processor = Processor.Processor(stylesheetAltUris = [OsPathToUri(pipp_dir + os.path.sep)])
    processor.registerExtensionModules(['pipp_xslt'])
    stylesheet = InputSource.DefaultFactory.fromUri(OsPathToUri(in_root + stylesheet_fname))
    processor.appendStylesheet(stylesheet)

    processor.extensionParams[(NAMESPACE, 'in_root')] = in_root
    processor.extensionParams[(NAMESPACE, 'out_root')] = out_root
    processor.extensionParams[(NAMESPACE, 'state_xml')] = state_xml
    processor.extensionParams[(NAMESPACE, 'state_doc')] = state_doc

    #--
    # Go through all pages in state xml
    #--
    for page in state_doc.xpath('//page'):
                
        src = Conversions.StringValue(page.attributes[(EMPTY_NAMESPACE, 'src')])
        in_path = abs_in_path(processor, src)
        out_path = re.sub('\.pip$', '.html', abs_out_path(processor, in_path))        
        build_time = os.stat(out_path).st_mtime
        
        deps = [src] + [x.firstChild.nodeValue for x in page.xpath('depends/depend')]
        if any(os.stat(abs_in_path(processor, d)).st_mtime > build_time for d in deps):
        
            #--
            # If any dependent files have a newer modification time than the target, rebuild
            #--
            processor.extensionParams[(NAMESPACE, 'read_state_node')] = page
            state_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
            state_node.setAttributeNS(EMPTY_NAMESPACE, 'src', src)
            build_file(processor, state_node)
            
            # TBD: save changes to state            

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
    in_root = processor.extensionParams[(NAMESPACE, 'in_root')]
    out_root = processor.extensionParams[(NAMESPACE, 'out_root')]
    state_doc = processor.extensionParams[(NAMESPACE, 'state_doc')]

    #--
    # Locate the input file and read it
    #--
    input_file = state_node.getAttributeNS(EMPTY_NAMESPACE, 'src')
    input = InputSource.DefaultFactory.fromUri(OsPathToUri(in_root + input_file))
    output_file = re.sub('\.pip$', '.html', input_file)

    #--
    # Pass required information to XSLT extention functions
    #--
    processor.extensionParams[(NAMESPACE, 'file_name')] = input_file
    processor.extensionParams[(NAMESPACE, 'out_file')] = output_file
    processor.extensionParams[(NAMESPACE, 'state_node')] = state_node

    #--
    # Create structural nodes in state document, to be filled during processing
    #--
    for node_name in ['exports', 'depends', 'children']:
        new_node = state_doc.createElementNS(EMPTY_NAMESPACE, node_name)
        state_node.appendChild(new_node)
        processor.extensionParams[(NAMESPACE, node_name + '_node')] = new_node

    #--
    # Run the XSLT processor
    #--
    try:
        output = processor.run(input)
    except Exception, e:
        print 'Error: exception occured while processing %s:\n%s' % (input_file, e)
        sys.exit(1)

    #--
    # Determine the output file name and write output to it
    #--
    abs_output_file = abs_out_path(processor, abs_in_path(processor, output_file))
    output_fh = open(abs_output_file, 'w')
    output_fh.write(output)
    output_fh.close()

    #--
    # Process all this file's children. If the child already has child nodes in
    # the state dom, it is a "child-file" and not processed.
    #--
    if do_children:
        children_node = processor.extensionParams[(NAMESPACE, 'children_node')]
        for child in children_node.childNodes:
            if not child.hasChildNodes():
                processor.extensionParams[(NAMESPACE, 'read_state_node')] = child
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
    rebuild_project(project_fname)
elif len(sys.argv) == 3 and sys.argv[1] == '-f':
    project_fname = '%s/%s.xml' % (project_dir, sys.argv[2])
    build_project(project_fname)

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
