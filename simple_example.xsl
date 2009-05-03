<?xml version="1.0"?>

<xsl:stylesheet
    xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
    xmlns:pipp="http://pajhome.org.uk/web/pipp/xml-namespace"
    extension-element-prefixes="pipp"
    version="1.0">
<xsl:import href="pipp.xsl"/>
<xsl:output indent="no" method="html"/>

<xsl:template match="/pipp/body">
    <xsl:value-of select="pipp:file('/style.css')"/>
    <html>
        <head>
            <title><xsl:value-of select="pipp:import-join('title', ': ')"/></title>
            <link rel="stylesheet" href="{pipp:relative-path('/style.css')}"/>
        </head>
        <body>
            <xsl:apply-templates/>
        </body>
    </html>
</xsl:template>

</xsl:stylesheet>
