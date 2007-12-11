<?xml version="1.0"?>
<!--
 ! Pipp basic stylesheet
 !-->
<xsl:stylesheet
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:pipp="http://pajhome.org.uk/web/pipp/xml-namespace"
  extension-element-prefixes="pipp"
  version="1.0">

<!--
 ! Identity transform. This causes unmatched tags to pass through unchanged.
 !-->
<xsl:template match="@*|*">
  <xsl:copy>
    <xsl:apply-templates select="*|@*|text()"/>
  </xsl:copy>
</xsl:template>

<!--
 ! This template matches the whole pipp document. The <body> tag is processed
 ! for its content, while all other tags become exported variables.
 !-->
<xsl:template match="pipp">
  <xsl:for-each select="*[name() != 'body']">
    <xsl:value-of select="pipp:export(name(), text())"/>
  </xsl:for-each>
  <xsl:if test="not(link)">
    <xsl:value-of select="pipp:export('link', pipp:file-name())"/>
  </xsl:if>
  <xsl:apply-templates select="body"/>
</xsl:template>

<!--
 ! The following templates are thin wrappers around Pipp functions.
 !-->
<xsl:template match="pipp-child">
  <xsl:value-of select="pipp:child(@src)"/>
</xsl:template>

<xsl:template match="pipp-file">
  <xsl:value-of select="pipp:file(@src)"/>
</xsl:template>

<xsl:template match="pipp-child-file">
  <xsl:value-of select="pipp:child-file(@src, @title)"/>
</xsl:template>

<xsl:template match="pipp-code">
  <xsl:value-of disable-output-escaping="yes" select="pipp:code(@src)"/>
</xsl:template>

<xsl:template match="pipp-map-view">
  <xsl:value-of disable-output-escaping="yes" select="pipp:map-view(@src)"/>
</xsl:template>

<!--
 ! Automatically fill-in width and height tags for images
 !-->
<xsl:template match="pipp-img" name="pipp-img">
  <xsl:value-of select="pipp:file(@src)"/>
  <img width="{pipp:image-width(@src)}" height="{pipp:image-height(@src)}">
    <xsl:apply-templates select="@*"/>
  </img>
</xsl:template>

<!--
 ! Generate thumbnails for images with specified size
 !-->
<xsl:template match="pipp-thumb">
  <xsl:value-of select="pipp:file(@src)"/>
  <a href="{@src}">
    <xsl:variable name="thumb" select="pipp:thumbnail(@src, @width, @height)"/>
    <img src="{$thumb}" width="{pipp:image-width($thumb)}" height="{pipp:image-height($thumb)}">
      <xsl:apply-templates select="@*[name() != 'src' and name() != 'width' and name() != 'height']"/>
    </img>
  </a>
</xsl:template>

</xsl:stylesheet>
