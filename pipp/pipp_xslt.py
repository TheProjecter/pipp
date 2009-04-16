#!/usr/bin/python
#--
# This file defines the Pipp XPath extension functions.
#--
from Ft.Xml import InputSource, EMPTY_NAMESPACE
from Ft.Xml.Xslt import Processor
from Ft.Xml.XPath import Conversions
from Ft.Lib.Uri import OsPathToUri
from pipp_utils import *
import os, re, string, time, glob, stat, shutil
import Image, ImageDraw, ImageFont
from pygments import highlight
from pygments.lexers import get_lexer_for_filename, get_lexer_by_name
from pygments.formatters import HtmlFormatter

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
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    file_name = ctx.abs_in_path(Conversions.StringValue(file_name)) \
                                [len(ctx.in_root):]
    new_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
    new_node.setAttributeNS(EMPTY_NAMESPACE, 'src', file_name)
    ctx.children_node.appendChild(new_node)

#--
# Copy a file from in-root to out-root. For efficiency it keeps track of the
# files it has already done and won't repeat these. This function uses the glob
# module to support wildcards in file names.
#--
def pipp_file(context, file_name):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    file_name = Conversions.StringValue(file_name)
    file_names = glob.glob(ctx.abs_in_path(file_name))
    if len(file_names) == 0:
        raise Exception('No files found: ' + file_name)
    if len(file_names) == 1:
        ctx.add_depends(file_names[0][len(ctx.in_root):])
    for in_name in file_names:
        out_name = ctx.abs_out_path(in_name)
        if not files.has_key(in_name):
            if os.path.isfile(in_name):
                shutil.copyfile(in_name, out_name)
            else:
                copytree(in_name, out_name, skip_copy)
            files[in_name] = 1

#--
# Copy a file from in-root to out-root, and also add it to the state DOM.
# This function does not support wildcards in file names.
#--
def pipp_child_file(context, src, title):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]

    #--
    # Copy the file, using a cache for efficiency
    #--
    in_name = Conversions.StringValue(src)
    if in_name.startswith('http'):
        link_name = in_name
    else:
        in_name = ctx.abs_in_path(in_name)
        out_name = ctx.abs_out_path(in_name)
        link_name = out_name[len(ctx.out_root):]
        if not files.has_key(in_name):
            out_fh = open(out_name, 'wb')
            out_fh.write(open(in_name, 'rb').read())
            out_fh.close()
            files[in_name] = 1

    #--
    # Update the state DOM
    #--
    new_page_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'page')
    new_page_node.setAttributeNS(EMPTY_NAMESPACE, 'src', in_name[len(ctx.in_root):])
    new_exports_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'exports')
    new_title_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'title')
    new_title_node.appendChild(ctx.state_doc.createTextNode(Conversions.StringValue(title)))
    new_link_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, 'link')
    new_link_node.appendChild(ctx.state_doc.createTextNode(link_name))

    new_exports_node.appendChild(new_title_node)
    new_exports_node.appendChild(new_link_node)
    new_page_node.appendChild(new_exports_node)
    ctx.children_node.appendChild(new_page_node)

#--
# Export a variable from the current page, storing it in the state DOM.
#--
def pipp_export(context, name, value):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    new_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, Conversions.StringValue(name))
    new_node.appendChild(ctx.state_doc.createTextNode(Conversions.StringValue(value)))
    ctx.exports_node.appendChild(new_node)

#--
# Import an exported variable. If this isn't defined by the current file, the
# function searches up the page tree until it finds a definition.
#--
def pipp_import(context, name):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    name = Conversions.StringValue(name)
    cur_doc = ctx.state_node
    while cur_doc:
        ctx.add_edepends(cur_doc.getAttributeNS(EMPTY_NAMESPACE, 'src'), name)
        nodes = cur_doc.xpath("exports/*[name()='%s']" % name.replace("'", ""))
        if nodes:
            return get_text(nodes[0])
        cur_doc = cur_doc.parentNode.parentNode
    raise Exception("Import not found")

#--
# Import all versions of an exported variable from the current document and its
# ancestors. The values are joined into a single string using the given
# separator.
#--
def pipp_import_join(context, name, join_str):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    name = Conversions.StringValue(name)
    cur_doc = ctx.state_node
    values = []
    while cur_doc:
        ctx.add_edepends(cur_doc.getAttributeNS(EMPTY_NAMESPACE, 'src'), name)
        nodes = cur_doc.xpath("exports/*[name()='%s']" % name.replace("'", ""))
        if nodes:
            values.insert(0, get_text(nodes[0]))
        cur_doc = cur_doc.parentNode.parentNode
    return Conversions.StringValue(join_str).join(values)

#--
# Add a dependency on an exported variable
#--
def pipp_export_depend(context, src, export):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    ctx.add_edepends(Conversions.StringValue(src), Conversions.StringValue(export))

#--
# Create a view of the site map. This runs an XSLT stylesheet against the XML
# state file.
#--
def pipp_map_view(context, xslt_file):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]

    #--
    # Create the XSLT processor object. For efficiency there is a cache of these.
    #--
    xslt_file = ctx.abs_in_path(Conversions.StringValue(xslt_file))
    ctx.add_depends(xslt_file[len(ctx.in_root):])
    processor = processors.get(xslt_file)
    if not processor:
        processor = Processor.Processor()
        processor.registerExtensionModules(['pipp_xslt'])
        processor.appendStylesheet(InputSource.DefaultFactory.fromString(open(xslt_file).read(), xslt_file))
    processor.extensionParams[(NAMESPACE, 'context')] = ctx

    #--
    # Run the processor against state.xml and return the output.
    # If successful, store the processor object in a cache
    #--
    input = InputSource.DefaultFactory.fromUri(OsPathToUri(ctx.state_xml))
    output = processor.run(input)
    processors[xslt_file] = processor
    return output

#--
# Get the current file name.
#--
def pipp_file_name(context):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    return ctx.out_file

#--
# Display the last modification time of the current file, using the provided
# date format string.
#--
def pipp_file_time(context, fmt):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    fmt = Conversions.StringValue(fmt)
    fname = ctx.in_root + ctx.file_name
    return time.strftime(fmt, time.localtime(os.stat(fname).st_mtime))

#--
# Given a path relative to in_root, return a path relative to current file
# Note that os.path.commonprefix works on a character basis so the regex that
# follows it is necessary to handle the cases where directories start with the
# same letter.
#--
def pipp_relative_path(context, link):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    link = Conversions.StringValue(link)
    if len(link) == 0: return ''
    if link[0] != '/': return link
    link_path = ctx.in_root + link
    file_path = os.path.dirname(ctx.in_root + ctx.file_name) + '/'

    common_prefix = os.path.commonprefix([file_path, link_path])
    common_prefix = re.sub('[^/]*$', '', common_prefix)
    depth = string.count(file_path[len(common_prefix):], '/')
    return '../' * depth + link_path[len(common_prefix):]

#--
# Render source code as syntax highlighted HTML. This works by calling the
# perl script "code2html".
#--
def pipp_code(context, src, code, lexer, docss):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]

    src = Conversions.StringValue(src)
    if src:
        abs_src = ctx.abs_in_path(src)
        ctx.add_depends(abs_src[len(ctx.in_root):])
        fname = os.path.basename(src)
        code = open(abs_src).read()
    else:
        fname = 'inline-code'
        code = Conversions.StringValue(code)

    lexer = Conversions.StringValue(lexer)
    if lexer:
        lexer = get_lexer_by_name(lexer)
    elif src:
        lexer = get_lexer_for_filename(fname)
    else:
        raise Exception('The lexer must be explicitly specified for inline code blocks')

    formatter = HtmlFormatter(cssclass="source")
    result = highlight(code, lexer, formatter)
    if Conversions.StringValue(docss) == '1':
        result = '<link rel="stylesheet" href="%s.css"/>' % fname + result
        css = open(ctx.abs_out_path(ctx.abs_in_path(fname + '.css')), 'w')
        css.write(formatter.get_style_defs())
        css.close()

    return result

#--
# Functions to determine the width and height of an image file, using PIL.
# For efficiency they keep a cache of open image objects.
#--
def pipp_image_width(context, src):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    image_name = ctx.abs_in_path(Conversions.StringValue(src))
    if not images.has_key(image_name):
        images[image_name] = Image.open(image_name)
    return images[image_name].size[0]

def pipp_image_height(context, src):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    image_name = ctx.abs_in_path(Conversions.StringValue(src))
    if not images.has_key(image_name):
        images[image_name] = Image.open(image_name)
    return images[image_name].size[1]

#--
# Create a thumbnail of an image, at the specified size.
#--
def pipp_thumbnail(context, src, width, height):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    image_name = ctx.abs_in_path(Conversions.StringValue(src))
    ctx.add_depends(image_name[len(ctx.in_root):])
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
    img.save(ctx.abs_out_path(ctx.abs_in_path(thumb_name)))

    #--
    # Add image to cache using fake inroot name, so width/height functions work
    #--
    images[ctx.abs_in_path(thumb_name)] = img

    return thumb_name

#--
# Create a page title image, rendering text in a truetype font and using a
# bitmap texture. The image is created as RGBA to get anti-aliased quality,
# but output as a 256-color paletted image for size and transparency.
# The background colour must be specified for anti-aliasing to work properly.
#--
def pipp_gtitle(context, font, height, texture, bgcolor, text):
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]

    ctx.add_depends(Conversions.StringValue(font))
    ctx.add_depends(Conversions.StringValue(texture))

    #--
    # Convert the XSLT parameters into regular python types
    #--
    font = ctx.abs_in_path(Conversions.StringValue(font))
    height = int(Conversions.NumberValue(height))
    texture = ctx.abs_in_path(Conversions.StringValue(texture))
    bgcolor = int(Conversions.StringValue(bgcolor)[1:], 16)
    text = Conversions.StringValue(text)
    file_name = re.sub('[^a-zA-Z0-9]', '_', text) + '.png'
    pseudo_in_name = ctx.abs_in_path(file_name)

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
    out.save(ctx.abs_out_path(pseudo_in_name), transparency=0)

    #--
    # Add image to cache using fake inroot name, so width/height functions work
    #--
    images[pseudo_in_name] = out

    return file_name


def pipp_link(context, link):
    """Record a link"""
    ctx = context.processor.extensionParams[(NAMESPACE, 'context')]
    new_node = ctx.state_doc.createElementNS(EMPTY_NAMESPACE, Conversions.StringValue('link'))
    new_node.appendChild(ctx.state_doc.createTextNode(Conversions.StringValue(link)))
    ctx.links_node.appendChild(new_node)
    # TBD: avoid dupes

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
    (NAMESPACE, 'export-depend'):   pipp_export_depend,
    (NAMESPACE, 'map-view'):        pipp_map_view,
    (NAMESPACE, 'link'):            pipp_link,

    (NAMESPACE, 'file-name'):       pipp_file_name,
    (NAMESPACE, 'file-time'):       pipp_file_time,
    (NAMESPACE, 'relative-path'):   pipp_relative_path,
    (NAMESPACE, 'code'):            pipp_code,

    (NAMESPACE, 'image-width'):     pipp_image_width,
    (NAMESPACE, 'image-height'):    pipp_image_height,
    (NAMESPACE, 'thumbnail'):       pipp_thumbnail,
    (NAMESPACE, 'gtitle'):          pipp_gtitle,
}
