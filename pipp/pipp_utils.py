#!/usr/bin/python
#--
# Functions and constants common to all Pipp modules
#--
import os, warnings, sys, re

#--
# Configuration
#--
NAMESPACE     = 'http://pajhome.org.uk/web/pipp/xml-namespace'
perl_cmd      = 'c:\\perl\\bin\\perl.exe' # only needed on Windows

#--
# Determine program directory
#--
pipp_dir      = os.path.abspath(os.path.dirname(sys.argv[0]))
project_dir   = os.path.join(pipp_dir, 'projects')

#--
# Given a pipp path, return the absolute path in the input tree. If the path
# is relative, it is relative to the current file. If it is absolute then the
# in-root is prepended.
#--
def abs_in_path(processor, file_name):
  if file_name[0] == '/':
    return processor.extensionParams[(NAMESPACE, 'in_root')] + file_name
  else:
    return os.path.dirname(processor.extensionParams[(NAMESPACE, 'in_root')] + \
        processor.extensionParams[(NAMESPACE, 'file_name')]) + '/' + file_name

#--
# Given an absolute input path, return the absolute output path. If the output
# directories do not exist then this function will create them.
#--
def abs_out_path(processor, in_path):
  abs_output_file = processor.extensionParams[(NAMESPACE, 'out_root')] + \
         in_path[len(processor.extensionParams[(NAMESPACE, 'in_root')]):]
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
