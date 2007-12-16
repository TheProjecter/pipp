#!/usr/bin/python
#--
# Functions and constants common to all Pipp modules
#--
import os, warnings, sys, re, shutil
from Ft.Xml import EMPTY_NAMESPACE

#--
# Configuration
#--
NAMESPACE   = 'http://pajhome.org.uk/web/pipp/xml-namespace'
perl_cmd    = 'c:\\perl\\bin\\perl.exe' # only needed on Windows
skip_copy   = ['.svn']

#--
# Determine program directory
#--
pipp_dir    = os.path.abspath(os.path.dirname(sys.argv[0]))
project_dir = os.path.join(pipp_dir, 'projects')

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
# Copy a directory tree, excluding certain names
#--
def copytree(src, dst, skip):
    shutil.rmtree(dst)
    for dirpath, dirnames, filenames in os.walk(src):
        for s in skip:
            dirnames.remove(s)
        dstpath = dst + dirpath[len(src):]
        if not os.path.isdir(dstpath):
            os.mkdir(dstpath)
        for f in filenames:
            shutil.copyfile(os.path.join(dirpath, f), os.path.join(dstpath, f))
