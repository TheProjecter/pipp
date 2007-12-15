#!/usr/bin/python
#--
# This file defines the Pipp XPath extension functions.
#--
from Ft.Xml import InputSource, EMPTY_NAMESPACE
from Ft.Xml.Xslt import Processor
from Ft.Xml.XPath import Conversions
from Ft.Lib.Uri import OsPathToUri
from pipp_utils import *
import os, re, string, time, glob, stat
import Image, ImageDraw, ImageFont

#--
# Caches
#--
images = {}
processors = {}
files = {}

#--
# Add a pipp file as a child of the current file. This function adds it to
# the state DOM; the main pipp process will notice this and build the file.
#--
def pipp_child(context, file_name):
    file_name = abs_in_path(context.processor, Conversions.StringValue(file_name)) \
                                [len(context.processor.extensionParams[(NAMESPACE, 'in_root')]):]
    state_doc = context.processor.extensionParams[(NAMESPACE, 'state_doc')]
    children_node = context.processor.extensionParams[(NAMESPACE, 'children_node')]
    new_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
    new_node.setAttributeNS(EMPTY_NAMESPACE, 'src', file_name)
    children_node.appendChild(new_node)

#--
# Copy a file from in-root to out-root. For efficiency it keeps track of the
# files it has already done and won't repeat these. This function uses the glob
# module to support wildcards in file names.
#--
def pipp_file(context, file_name):
    file_name = Conversions.StringValue(file_name)
    file_names = glob.glob(abs_in_path(context.processor, file_name))
    if len(file_names) == 0:
        raise Exception('No files found: ' + file_name)
    in_root = context.processor.extensionParams[(NAMESPACE, 'in_root')]
    for in_name in file_names:
        add_depends(context, in_name[len(in_root):])
        out_name = abs_out_path(context.processor, in_name)
        if not files.has_key(in_name):
            out_fh = open(out_name, 'wb')
            out_fh.write(open(in_name, 'rb').read())
            out_fh.close()
            files[in_name] = 1

#--
# Copy a file from in-root to out-root, and also add it to the state DOM.
# This function does not support wildcards in file names.
#--
def pipp_child_file(context, src, title):

    #--
    # Copy the file, using a cache for efficiency
    #--
    in_name = Conversions.StringValue(src)
    if in_name.startswith('http'):
        link_name = in_name
    else:
        in_name = abs_in_path(context.processor, in_name)
        out_name = abs_out_path(context.processor, in_name)
        link_name = out_name[len(context.processor.extensionParams[(NAMESPACE, 'out_root')]):]
        if not files.has_key(in_name):
            out_fh = open(out_name, 'wb')
            out_fh.write(open(in_name, 'rb').read())
            out_fh.close()
            files[in_name] = 1

    #--
    # Update the state DOM
    #--
    state_doc = context.processor.extensionParams[(NAMESPACE, 'state_doc')]

    new_page_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
    new_page_node.setAttributeNS(EMPTY_NAMESPACE, 'src', in_name[len(context.processor.extensionParams[(NAMESPACE, 'in_root')]):])
    new_exports_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'exports')
    new_title_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'title')
    new_title_node.appendChild(state_doc.createTextNode(Conversions.StringValue(title)))
    new_link_node = state_doc.createElementNS(EMPTY_NAMESPACE, 'link')
    new_link_node.appendChild(state_doc.createTextNode(link_name))

    new_exports_node.appendChild(new_title_node)
    new_exports_node.appendChild(new_link_node)
    new_page_node.appendChild(new_exports_node)
    context.processor.extensionParams[(NAMESPACE, 'children_node')].appendChild(new_page_node)

#--
# Export a variable from the current page, storing it in the state DOM.
#--
def pipp_export(context, name, value):
    state_doc = context.processor.extensionParams[(NAMESPACE, 'state_doc')]
    exports_node = context.processor.extensionParams[(NAMESPACE, 'exports_node')]
    new_node = state_doc.createElementNS(EMPTY_NAMESPACE, Conversions.StringValue(name))
    new_node.appendChild(state_doc.createTextNode(Conversions.StringValue(value)))
    exports_node.appendChild(new_node)

#--
# Import an exported variable. If this isn't defined by the current file, the
# function searches up the page tree until it finds a definition.
#--
def pipp_import(context, name):
    name = Conversions.StringValue(name)
    cur_doc = context.processor.extensionParams[(NAMESPACE, 'read_state_node')]
    while cur_doc:
        cur_exp = [x for x in cur_doc.childNodes if getattr(x, 'tagName', None) == 'exports'][0]
        for node in cur_exp.childNodes:
            if getattr(node, 'tagName', None) == name:
                return get_text(node)
        cur_doc = cur_doc.parentNode.parentNode
    raise Exception("Import not found")

#--
# Import all versions of an exported variable from the current document and its
# ancestors. The values are joined into a single string using the given
# separator.
#--
def pipp_import_join(context, name, join_str):
    name = Conversions.StringValue(name)
    cur_doc = context.processor.extensionParams[(NAMESPACE, 'read_state_node')]
    values = []
    while cur_doc:
        cur_exp = [x for x in cur_doc.childNodes if getattr(x, 'tagName', None) == 'exports'][0]
        for node in cur_exp.childNodes:
            if getattr(node, 'tagName', None) == name:
                values.insert(0, get_text(node))
        cur_doc = cur_doc.parentNode.parentNode
    return Conversions.StringValue(join_str).join(values)

#--
# Create a view of the site map. This runs an XSLT stylesheet against the XML
# state file.
#--
def pipp_map_view(context, xslt_file):

    #--
    # Create the XSLT processor object. For efficiency there is a cache of these.
    #--
    xslt_file = abs_in_path(context.processor, Conversions.StringValue(xslt_file))
    if not processors.has_key(xslt_file):
        processors[xslt_file]= Processor.Processor()
        processors[xslt_file].registerExtensionModules(['pipp_xslt'])
        processors[xslt_file].appendStylesheet(InputSource.DefaultFactory.fromString(open(xslt_file).read(), xslt_file))

    #--
    # Copy variables relevant to current file from pipp processor to the map view
    # processor.
    #--
    for var in ['in_root', 'out_root', 'state_doc', 'read_state_node', 'state_node', 'file_name', 'out_file', 'depends_node']:
        processors[xslt_file].extensionParams[(NAMESPACE, var)] = context.processor.extensionParams[(NAMESPACE, var)]

    #--
    # Run the processor against state.xml and return the output.
    #--
    state_xml = context.processor.extensionParams[(NAMESPACE, 'state_xml')]
    input = InputSource.DefaultFactory.fromUri(OsPathToUri(state_xml))
    return processors[xslt_file].run(input)

#--
# Get the current file name.
#--
def pipp_file_name(context):
    return context.processor.extensionParams[(NAMESPACE, 'out_file')]

#--
# Display the last modification time of the current file, using the provided
# date format string.
#--
def pipp_file_time(context, fmt):
    fmt = Conversions.StringValue(fmt)
    fname = context.processor.extensionParams[(NAMESPACE, 'in_root')] + \
                    context.processor.extensionParams[(NAMESPACE, 'file_name')]
    return time.strftime(fmt, time.localtime(os.stat(fname)[stat.ST_MTIME]))

#--
# Given a path relative to in_root, return a path relative to current file
# Note that os.path.commonprefix works on a character basis so the regex that
# follows it is necessary to handle the cases where directories start with the
# same letter.
#--
def pipp_relative_path(context, link):
    link = Conversions.StringValue(link)
    if len(link) == 0: return ''
    if link[0] != '/': return link
    link_path = context.processor.extensionParams[(NAMESPACE, 'in_root')] + link
    file_path = os.path.dirname(context.processor.extensionParams[(NAMESPACE, 'in_root')] + \
                                                            context.processor.extensionParams[(NAMESPACE, 'file_name')]) + '/'

    common_prefix = os.path.commonprefix([file_path, link_path])
    common_prefix = re.sub('[^/]*$', '', common_prefix)
    depth = string.count(file_path[len(common_prefix):], '/')
    return '../' * depth + link_path[len(common_prefix):]

#--
# Render source code as syntax highlighted HTML. This works by calling the
# perl script "code2html".
#--
def pipp_code(context, src):
    abs_src = abs_in_path(context.processor, Conversions.StringValue(src))
    in_root = context.processor.extensionParams[(NAMESPACE, 'in_root')]
    add_depends(context, abs_src[len(in_root):])

    code2html_cmd = '%s/code2html -o html-css %s' % (pipp_dir, abs_src)
    if os.name == 'nt':
        code2html_cmd = perl_cmd + ' ' + code2html_cmd
    else:
        code2html_cmd += ' 2>/dev/null'

    pipe = os.popen(code2html_cmd)
    code_html = pipe.read()
    rc = pipe.close()
    if rc is not None:
        raise Exception('code2html failed: %d' % rc)
    return code_html

#--
# Functions to determine the width and height of an image file, using PIL.
# For efficiency they keep a cache of open image objects.
#--
def pipp_image_width(context, src):
    image_name = abs_in_path(context.processor, Conversions.StringValue(src))
    if not images.has_key(image_name):
        images[image_name] = Image.open(image_name)
    return images[image_name].size[0]

def pipp_image_height(context, src):
    image_name = abs_in_path(context.processor, Conversions.StringValue(src))
    if not images.has_key(image_name):
        images[image_name] = Image.open(image_name)
    return images[image_name].size[1]

#--
# Create a thumbnail of an image, at the specified size.
#--
def pipp_thumbnail(context, src, width, height):
    image_name = abs_in_path(context.processor, Conversions.StringValue(src))
    in_root = context.processor.extensionParams[(NAMESPACE, 'in_root')]
    add_depends(context, image_name[len(in_root):])
    thumb_name = re.sub('(\.\w+)$', '_thumb\g<1>', Conversions.StringValue(src))
    
    if width:
        width = int(Conversions.NumberValue(width))
    if height:
        height = int(Conversions.NumberValue(height))

    img = Image.open(image_name)
    w,h = img.size

    if height and not width:
        width = int(w * height / h)    
    if width and not height:
        height = int(h * width / w)    
    
    img = img.resize((width, height))
    img.save(abs_out_path(context.processor, abs_in_path(context.processor, thumb_name)))

    #--
    # Add image to cache using fake inroot name, so width/height functions work
    #--
    images[abs_in_path(context.processor, thumb_name)] = img

    return thumb_name

#--
# Create a page title image, rendering text in a truetype font and using a
# bitmap texture. The image is created as RGBA to get anti-aliased quality,
# but output as a 256-color paletted image for size and transparency.
# The background colour must be specified for anti-aliasing to work properly.
#--
def pipp_gtitle(context, font, height, texture, bgcolor, text):
    # Not that important
    #add_depends(context, Conversions.StringValue(font))
    #add_depends(context, Conversions.StringValue(texture))

    #--
    # Convert the XSLT parameters into regular python types
    #--
    font = abs_in_path(context.processor, Conversions.StringValue(font))
    height = int(Conversions.NumberValue(height))
    texture = abs_in_path(context.processor, Conversions.StringValue(texture))
    bgcolor = int(Conversions.StringValue(bgcolor)[1:], 16)
    text = Conversions.StringValue(text)
    file_name = re.sub('[^a-zA-Z0-9]', '_', text) + '.png'
    pseudo_in_name = abs_in_path(context.processor, file_name)

    # Avoid unwanted cropping on the left
    text = '    ' + text

    #--
    # Create the text mask
    #--
    im_font = ImageFont.truetype(font, height)
    text_mask = Image.new('RGBA', im_font.getsize(text), 0)
    text_mask_draw = ImageDraw.Draw(text_mask)
    text_mask_draw.text((0,0), text, font=im_font, fill=(0,0,0,0xFF))
    text_mask = text_mask.crop(text_mask.getbbox())

    #--
    # Create the background pattern
    #--
    texture = Image.open(texture)
    background = Image.new('RGBA', text_mask.size)
    for x in range(0, 1 + text_mask.size[0] / texture.size[0]):
        for y in range(0, 1 + text_mask.size[1] / texture.size[1]):
            background.paste(texture, (x * texture.size[0], y * texture.size[1]))

    #--
    # Create the final image
    #--
    out = Image.new('RGBA', text_mask.size, bgcolor)
    out.paste(background, (0, 0), text_mask)
    out = out.convert('P')    
    out.save(abs_out_path(context.processor, pseudo_in_name), transparency=0)

    #--
    # Add image to cache using fake inroot name, so width/height functions work
    #--
    images[pseudo_in_name] = out

    return file_name

#--
# Register all the extension functions with the XSLT processor.
#--
ExtFunctions = \
{
    (NAMESPACE, 'child'):           pipp_child,
    (NAMESPACE, 'file'):            pipp_file,
    (NAMESPACE, 'child-file'):      pipp_child_file,

    (NAMESPACE, 'export'):          pipp_export,
    (NAMESPACE, 'import'):          pipp_import,
    (NAMESPACE, 'import-join'):     pipp_import_join,
    (NAMESPACE, 'map-view'):        pipp_map_view,

    (NAMESPACE, 'file-name'):       pipp_file_name,
    (NAMESPACE, 'file-time'):       pipp_file_time,
    (NAMESPACE, 'relative-path'):   pipp_relative_path,
    (NAMESPACE, 'code'):            pipp_code,

    (NAMESPACE, 'image-width'):     pipp_image_width,
    (NAMESPACE, 'image-height'):    pipp_image_height,
    (NAMESPACE, 'thumbnail'):       pipp_thumbnail,
    (NAMESPACE, 'gtitle'):          pipp_gtitle,
}
