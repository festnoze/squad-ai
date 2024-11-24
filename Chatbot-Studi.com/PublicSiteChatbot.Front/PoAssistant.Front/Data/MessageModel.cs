using System.Text.Json.Serialization;

namespace PoAssistant.Front.Data;

public record MessageModel
{
    public static string UserRole = "user";
    public static string AiRole = "assistant";
    [JsonPropertyName("role")]
    public string Role { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; set; }

    [JsonPropertyName("duration")]
    public int DurationSeconds { get; set; }

    public DateTime Timestamp { get; init; }

    public bool IsSender => Role != UserRole;

    public bool IsLastConversationMessage { get; private set; } = false;

    public bool IsStreaming { get; set; } = false;

    public bool IsSavedMessage { get; set; }

    public bool IsEndMessage { get; set; } = false;

    public void SetAsLastThreadMessage () => IsLastConversationMessage = true;
    public bool SetAsLNotLastThreadMessage() => IsLastConversationMessage = false;

    public MessageModel(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isEndMessage = false)
    {
        //TODO ETM: change the roles names: user -> BusinessExpert, assistant -> PM
        if (source == "PM") source = AiRole;
        if (source.StartsWith("Business")) source = UserRole;

        Role = source;
        Content = content;
        DurationSeconds = durationSeconds;
        Timestamp = DateTime.Now;
        IsSavedMessage = isSavedMessage;
        IsEndMessage = isEndMessage;
        IsStreaming = false;
    }

    public void ChangeContent(string newContent)
    {
        this.Content = newContent;
    }
}
