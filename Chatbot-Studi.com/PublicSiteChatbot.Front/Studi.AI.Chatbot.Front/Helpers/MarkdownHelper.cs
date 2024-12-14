using Markdig;
using Markdig.Syntax.Inlines;
using Markdig.Syntax;
using Markdig.Renderers.Html;
using Markdig.Renderers;
using Markdig.Extensions.Tables;

namespace Studi.AI.Chatbot.Front.Helpers;

public static class MarkdownHelper
{
    private static MarkdownPipeline markdownPipeline =
                    new MarkdownPipelineBuilder()
                    .UseSoftlineBreakAsHardlineBreak()
                    .UseAdvancedExtensions()
                    .Build();

    public static string GetMarkdownContentConvertedToHtml(string content)
    {
        var input = content.TrimEnd();
        if (string.IsNullOrEmpty(input))
            return "";

        var document = Markdown.Parse(input, markdownPipeline);

        // Make all links open up in a new tab by adding them a target="_blank" attribute
        foreach (var link in document.Descendants().OfType<LinkInline>())
            link.GetAttributes().AddPropertyIfNotExist("target", "_blank");

        // Add styling to display arrays
        foreach (var table in document.Descendants().OfType<Table>())
            table.GetAttributes().AddClass("generated-array-class");

        foreach (var heading in document.Descendants().OfType<HeadingBlock>())
            if (heading.Level <= 3)
                heading.Level = 4; // Change h1, h2 and h3 to: h4

        // Render the Markdown document into HTML
        var result = "";
        using (var writer = new StringWriter())
        {
            var renderer = new HtmlRenderer(writer);
            markdownPipeline.Setup(renderer);
            renderer.Render(document);
            result = writer.ToString();
        }

        // Additional transformations        
        result = result.Replace("</ul>", "</ul><br>");// Add an extra line break (or paragraph spacing) after each </li> in the ordered list
        result = result.TrimEnd().Replace("</p>\n", "</p><br>");

        return result;
    }
}
