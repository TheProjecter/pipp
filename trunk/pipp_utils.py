#!/usr/bin/python
#--
# Functions and constants common to all Pipp modules
#--
import os, sys, shutil

NAMESPACE   = 'http://pajhome.org.uk/web/pipp/xml-namespace'
skip_copy   = ['.svn', '.pip']
pipp_dir    = os.path.abspath(os.path.dirname(sys.argv[0]))

def get_text(node):
    """This functions finds all the text node children of a DOM node and
    returns them joined into a single string."""
    rc = ''
    for text_node in node.childNodes:
        if text_node.nodeType == text_node.TEXT_NODE:
            rc = rc + text_node.data
    return rc


def do_skip(l, skip):
    todel = []
    for s in skip:
        for n in l:
            if n.endswith(s):
                todel.append(n)
    for n in todel:
        l.remove(n)
    

def copytree(src, dst, skip):
    "Copy a directory tree, excluding certain names"
    if os.path.exists(dst):
        shutil.rmtree(dst)
    for dirpath, dirnames, filenames in os.walk(src):
        do_skip(dirnames, skip)
        do_skip(filenames, skip)
        dstpath = dst + dirpath[len(src):]
        if not os.path.isdir(dstpath):
            os.mkdir(dstpath)
        for f in filenames:
            shutil.copyfile(os.path.join(dirpath, f), os.path.join(dstpath, f))
