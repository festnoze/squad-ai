using Studi.AI.Chatbot.Front.Helpers;
using System.Text.Json.Serialization;

namespace Studi.AI.Chatbot.Front.Models;

public record MessageModel
{
    public static string UserRole = "Utilisateur";
    public static string AiRole = "Assistant";

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
                _htmlContent = MarkdownHelper.GetMarkdownContentConvertedToHtml(this.Content);
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
