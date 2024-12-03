using System.Text.Json.Serialization;
using Markdig;
using Markdig.Syntax.Inlines;
using Markdig.Syntax;
using Markdig.Renderers.Html;
using Markdig.Renderers;
using Markdig.Extensions.Tables;

namespace Studi.AI.Chatbot.Front.Data;

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
    public bool IsEmpty => this.Content.Trim().Length == 0;

    public bool IsLastMessageOfConversation { get; private set; } = false;

    public bool IsStreaming { get; set; } = false;

    public bool IsSavedMessage { get; set; }

    public void SetAsLastConversationMessage () => IsLastMessageOfConversation = true;
    public bool SetAsNotLastConversationMessage() => IsLastMessageOfConversation = false;

    public MessageModel(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isStreaming = false)
    {
        Id = Guid.NewGuid();

        if (source == MessageModel.AiRole) 
            source = AiRole;
        if (source == MessageModel.UserRole) 
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
        this.Content = newContent;
    }

    public void AddContent(string contentToAdd)
    {
        this.Content += contentToAdd;
    }

    public void RemoveLastWord() 
    {
        var newEndIndex = this.Content.LastIndexOf(" ");
        if (newEndIndex == this.Content.Length - 1)
            this.Content = this.Content.Trim();
            newEndIndex = this.Content.LastIndexOf(" ");
        
        if (newEndIndex == -1)
            this.Content = "";
        else
            this.Content = this.Content.Substring(0, newEndIndex);
    }

    public string GetMarkdownContentConvertedToHtml()
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
