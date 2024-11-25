using System.Text.Json.Serialization;

namespace PoAssistant.Front.Data;

public record MessageModel
{
    public static string UserRole = "Utilisateur";
    public static string AiRole = "Assistant IA";

    [JsonPropertyName("role")]
    public string Role { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; set; }

    [JsonPropertyName("duration")]
    public int DurationSeconds { get; set; }

    public DateTime Timestamp { get; init; }

    public bool IsFromAI => Role == AiRole;
    public bool IsFromUser => Role == UserRole;

    public bool IsLastConversationMessage { get; private set; } = false;

    public bool IsStreaming { get; set; } = false;

    public bool IsSavedMessage { get; set; }

    public void SetAsLastConversationMessage () => IsLastConversationMessage = true;
    public bool SetAsNotLastConversationMessage() => IsLastConversationMessage = false;

    public MessageModel(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isStreaming = false)
    {
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
}
