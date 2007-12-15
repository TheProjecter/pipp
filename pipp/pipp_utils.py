#!/usr/bin/python
#--
# Functions and constants common to all Pipp modules
#--
import os, warnings, sys, re
from Ft.Xml import EMPTY_NAMESPACE

#--
# Configuration
#--
NAMESPACE   = 'http://pajhome.org.uk/web/pipp/xml-namespace'
perl_cmd    = 'c:\\perl\\bin\\perl.exe' # only needed on Windows

#--
# Determine program directory
#--
pipp_dir    = os.path.abspath(os.path.dirname(sys.argv[0]))
project_dir = os.path.join(pipp_dir, 'projects')

#--
# Given a pipp path, return the absolute path in the input tree. If the path
# is relative, it is relative to the current file. If it is absolute then the
# in-root is prepended.
#--
def abs_in_path(ctx, file_name):
    if file_name[0] == '/':
        return ctx.in_root + file_name
    else:
        return os.path.dirname(ctx.in_root + ctx.file_name) + '/' + file_name

#--
# Given an absolute input path, return the absolute output path. If the output
# directories do not exist then this function will create them.
#--
def abs_out_path(ctx, in_path):
    abs_output_file = ctx.out_root + in_path[len(ctx.in_root):]
    if not os.path.isdir(os.path.dirname(abs_output_file)):
        os.makedirs(os.path.dirname(abs_output_file))
    return abs_output_file

#--
# This functions finds all the text node children of a DOM node and returns
# them joined into a single string.
#--
def get_text(node):
    rc = ''
    for text_node in node.childNodes:
        if text_node.nodeType == text_node.TEXT_NODE:
            rc = rc + text_node.data
    return rc

#--
# Add a dependency
#--
def add_depends(ctx, file_name):
    for node in ctx.depends_node.childNodes:
        if file_name == node.firstChild.nodeValue:
            return
    new_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'depend')
    new_node.appendChild(ctx.state_doc.createTextNode(file_name))
    ctx.depends_node.appendChild(new_node)
