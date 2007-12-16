<?xml version="1.0"?>
<xsl:stylesheet
  xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
  xmlns:pipp="http://pajhome.org.uk/web/pipp/xml-namespace"
  extension-element-prefixes="pipp"
  version="1.0">
<xsl:output indent="yes" method="html"/>

<xsl:variable name="current_page" select="pipp:import('link')"/>

<!--
 ! This template starts by matching the first page element and is then called
 ! recursively.
 !-->
<xsl:template match="/page" name="render_navbar">
  <xsl:param name="level" select="1"/>

  <!--
   ! Display the "bullet" image. Ideally this would be replaced by CSS, but
   ! browser support doesn't seem wide enough yet.
   !-->
  <xsl:if test="$level &gt; 1">
    <xsl:variable name="imgname" select="concat('/styles/map_', pipp:import('style'), '_l', $level, '.gif')"/>
    <xsl:value-of select="pipp:file($imgname)"/>
    <img src="{pipp:relative-path($imgname)}"
         width="{pipp:image-width($imgname)}"
         height="{pipp:image-height($imgname)}"/>
  </xsl:if>

  <!--
   ! Display the page title - a link unless it's the current page
   !-->
  <xsl:choose>
    <xsl:when test="exports/link = $current_page">
      <span class="level{$level} selected"><xsl:value-of select="exports/title"/></span>
    </xsl:when>
    <xsl:otherwise>
      <a class="level{$level}" href="{pipp:relative-path(exports/link)}">
        <xsl:value-of select="exports/title"/>
      </a>
    </xsl:otherwise>
  </xsl:choose>
  <br/>

  <!--
   ! If the active page is a descendent of the current page, recursively call
   ! tempalate for all children of the current page.
   !-->
  <xsl:if test="descendant-or-self::page[exports/link = $current_page]">
    <xsl:for-each select="children/page">
      <xsl:call-template name="render_navbar">
        <xsl:with-param name="level"><xsl:value-of select="$level + 1"/></xsl:with-param>
      </xsl:call-template>
    </xsl:for-each>
  </xsl:if>

</xsl:template>
</xsl:stylesheet>
