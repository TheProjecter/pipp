<?xml version="1.0"?>

<xsl:stylesheet
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:pipp="http://pajhome.org.uk/web/pipp/xml-namespace"
  extension-element-prefixes="pipp"
  version="1.0">
<xsl:import href="pipp.xsl"/>
<xsl:output indent="no" method="html"/>

<!--
 ! This is the main template
 !-->
<xsl:template match="/pipp/body">
  <xsl:value-of select="pipp:stylesheet('/styles/*.css')"/>

  <!--
   ! Create the HTML header, containing title, meta tags, etc.
   !-->
  <html>
    <head>
      <title><xsl:value-of select="pipp:import-join('title', ': ')"/></title>
      <meta name="keywords" content="{pipp:import('keywords')}"/>
      <meta name="description" content="{pipp:import('desc')}"/>
      <link rel="stylesheet" href="{pipp:relative-path('/styles/common.css')}"/>
      <link rel="stylesheet" href="{pipp:relative-path(concat('/styles/', pipp:import('style'), '.css'))}"/>
      <xsl:if test="@target"><base target="{@target}"/></xsl:if>
    </head>
    <body>
      <table style="width:100%"><tr>
        <!--
         ! Create the side bar, containing the hierarchial site map
         !-->
        <td style="width:170px">
          <xsl:variable name="sidebar" select="concat('/styles/', pipp:import('style'), '_side-bar.gif')"/>
          <p><img src="{pipp:relative-path($sidebar)}" width="{pipp:image-width($sidebar)}" height="{pipp:image-height($sidebar)}"/></p>
          <div class="navbar">
            <xsl:value-of disable-output-escaping="yes" select="pipp:map-view('/navbar.xsl')"/>
          </div>
          <p style="text-align:center">
            <xsl:variable name="logo" select="pipp:relative-path(concat('/logos/', pipp:import('logo')))"/>
            <xsl:value-of select="pipp:file($logo)"/>
            <img src="{$logo}" width="{pipp:image-width($logo)}" height="{pipp:image-height($logo)}"/><br/><br/>
            <xsl:if test="@sidebar">
              <xsl:apply-templates/>
            </xsl:if>

            <!--
             ! Google AdSense - not included in example
             !-->
          </p>
        </td>

        <!--
         ! Create the main body of the page
         !-->
        <xsl:if test="not(@sidebar)">
          <td>
            <xsl:call-template name="h1">
              <xsl:with-param name="text"><xsl:value-of select="pipp:import('title')"/></xsl:with-param>
            </xsl:call-template>
            <xsl:apply-templates/>
            <xsl:call-template name="hr"/>
            <p style="margin-top:5px;">&#169; Insert your copyright notice here! <b>Updated:</b> <xsl:value-of select="pipp:file-time('%d %b %Y')"/></p>
          </td>
        </xsl:if>
      </tr></table>
    </body>
  </html>
</xsl:template>

<!--
 ! Display top level headings as graphics
 !-->
<xsl:template match="h1" name="h1">
  <xsl:param name="text" select="text()"/>

  <xsl:variable name="src">
    <xsl:if test="pipp:import('style') = 'blue-white'">
      <xsl:value-of select="pipp:gtitle('/styles/iglook.ttf', 50, '/styles/blue-white-pattern.gif', '#FFFFFF', $text)"/>
    </xsl:if>
  </xsl:variable>

  <p style="text-align:center">
    <img src="{$src}" alt="{$text}" width="{pipp:image-width($src)}" height="{pipp:image-height($src)}"/>
  </p>
</xsl:template>

<!--
 ! These templates provide workarounds for CSS limitations: there is no
 ! equivalent of cellspacing, and <hr>s end up with an ugly border.
 !-->
<xsl:template match="table[@class = 'lined']">
  <xsl:copy>
    <xsl:attribute name="cellspacing">0</xsl:attribute>
    <xsl:apply-templates select="*|@*|text()"/>
  </xsl:copy>
</xsl:template>

<xsl:template match="hr" name="hr">
  <p style="margin-bottom:0"><table cellspacing="0" class="hr"><tr><td/></tr></table></p>
</xsl:template>

<!--
 ! These templates are just shortcuts to save typing
 !-->
<xsl:template match="tbd">
  <p><b>(Under construction)</b></p>
</xsl:template>

</xsl:stylesheet>
