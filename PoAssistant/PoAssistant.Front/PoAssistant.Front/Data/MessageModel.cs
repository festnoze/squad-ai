using System.Text.Json.Serialization;

namespace PoAssistant.Front.Data;

public record MessageModel
{
    [JsonPropertyName("source")]
    public string Source { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; set; }

    [JsonPropertyName("durationSeconds")]
    public int DurationSeconds { get; set; }

    public DateTime Timestamp { get; init; }

    public bool IsSender => Source == "MOE";

    public bool IsLastThreadMessage { get; private set; } = false;

    public bool IsSavedMessage { get; set; }

    public void SetAsLastThreadMessage () => IsLastThreadMessage = true;
    public bool SetAsLNotLastThreadMessage() => IsLastThreadMessage = false;

    public MessageModel(string source, string content, int durationSeconds, bool isSavedMessage = true)
    {
        Source = source;
        Content = content;
        DurationSeconds = durationSeconds;
        Timestamp = DateTime.Now;
        IsSavedMessage = isSavedMessage;
    }

    public void ChangeContent(string newContent)
    {
        this.Content = newContent;
    }
}
