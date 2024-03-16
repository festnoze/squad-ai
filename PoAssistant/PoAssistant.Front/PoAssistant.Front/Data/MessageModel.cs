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
    public void SetAsLastThreadMessage () => IsLastThreadMessage = true;
    public bool SetAsLNotLastThreadMessage() => IsLastThreadMessage = false;

    public MessageModel(string source, string content, int durationSeconds)
    {
        Source = source;
        Content = content;
        DurationSeconds = durationSeconds;
        Timestamp = DateTime.Now;
    }
}
