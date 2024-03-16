using System.Text.Json.Serialization;

namespace PoAssistant.Front.Data;

public record MessageModel
{
    [JsonPropertyName("source")]
    public string Source { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; set; }


    [JsonPropertyName("content")]
    public int DurationSeconds { get; set; }

    public DateTime TimeStamp { get; init; }

    public bool IsSender => Source == "MOE";

    public bool IsLastThreadMessage { get; private set; } = false;
    public bool SetAsLastThreadMessage () => IsLastThreadMessage = true;

    public MessageModel(string source, string content, int durationSeconds)
    {
        Source = source;
        Content = content;
        DurationSeconds = durationSeconds;
        TimeStamp = DateTime.Now;
    }
}
