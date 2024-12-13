using System.Text.Json.Serialization;
using Markdig;
using Markdig.Syntax.Inlines;
using Markdig.Syntax;
using Markdig.Renderers.Html;
using Markdig.Renderers;
using Markdig.Extensions.Tables;

namespace Studi.AI.Chatbot.Front.Models;

public record MessageModel
{
    public static string UserRole = "Utilisateur";
    public static string AiRole = "Assistant";
    private static MarkdownPipeline markdownPipeline =
                    new MarkdownPipelineBuilder()
                    .UseSoftlineBreakAsHardlineBreak()
                    .UseAdvancedExtensions()
                    .Build();

    [JsonPropertyName("id")]
    public Guid Id { get; init; }

    [JsonPropertyName("role")]
    public string Role { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; private set; }

    [JsonPropertyName("duration")]
    public int DurationSeconds { get; set; }

    public DateTime Timestamp { get; init; }

    public bool IsFromAI => Role == AiRole;
    public bool IsFromUser => Role == UserRole;
    public bool IsEmpty => Content.Trim().Length == 0;

    public bool IsLastMessageOfConversation { get; private set; } = false;

    public bool IsStreaming { get; set; } = false;

    public bool IsSavedMessage { get; set; }

    public void SetAsLastConversationMessage() => IsLastMessageOfConversation = true;
    public bool SetAsNotLastConversationMessage() => IsLastMessageOfConversation = false;

    private string? _htmlContent = null;
    public string HtmlContent
    {
        get
        {
            if (_htmlContent == null)
                _htmlContent = _getMarkdownContentConvertedToHtml();
            return _htmlContent;
        }
    }

    public MessageModel(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isStreaming = false)
    {
        Id = Guid.NewGuid();

        if (source == AiRole)
            source = AiRole;
        if (source == UserRole)
            source = UserRole;

        Role = source;
        Content = content;
        DurationSeconds = durationSeconds;
        Timestamp = DateTime.Now;
        IsSavedMessage = isSavedMessage;
        IsStreaming = isStreaming;
    }

    public void ChangeContent(string newContent)
    {
        Content = newContent;
        _htmlContent = null; // Force HTML regeneration
    }

    public void AddContent(string contentToAdd)
    {
        Content += contentToAdd;
        _htmlContent = null; // Force HTML regeneration
    }

    public void RemoveLastWord()
    {
        var newEndIndex = Content.LastIndexOf(" ");
        if (newEndIndex == Content.Length - 1)
            Content = Content.Trim();
        newEndIndex = Content.LastIndexOf(" ");

        if (newEndIndex == -1)
            Content = "";
        else
            Content = Content.Substring(0, newEndIndex);
    }

    private string _getMarkdownContentConvertedToHtml()
    {
        var input = Content.TrimEnd();
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

    private string PreprocessContentForMarkdown(string input)
    {
        if (string.IsNullOrWhiteSpace(input))
            return input;

        // Étape 1 : Remplacer les doubles sauts de ligne par un marqueur temporaire
        string tempMarker = "[[DOUBLE_NEWLINE]]";
        string processed = input.Replace("\n\n", tempMarker);

        // Étape 2 : Remplacer les simples sauts de ligne par des doubles
        processed = processed.Replace("\n", "\n\n");

        // Étape 3 : Restaurer les marqueurs temporaires en doubles sauts de ligne
        processed = processed.Replace(tempMarker, "  \n\n");

        return processed;
    }
}
