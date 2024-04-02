using System.Text.Json.Serialization;

namespace PoAssistant.Front.Data;

public record MessageModel
{
    public static string BusinessExpertName = "Métier";
    public static string ProjectManagerName = "Chef de Projet";
    [JsonPropertyName("source")]
    public string Source { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; set; }

    [JsonPropertyName("duration")]
    public int DurationSeconds { get; set; }

    public DateTime Timestamp { get; init; }

    public bool IsSender => Source != BusinessExpertName;

    public bool IsLastThreadMessage { get; private set; } = false;

    public bool IsStreaming { get; set; } = false;

    public bool IsSavedMessage { get; set; }

    public bool IsEndMessage { get; set; } = false;

    public void SetAsLastThreadMessage () => IsLastThreadMessage = true;
    public bool SetAsLNotLastThreadMessage() => IsLastThreadMessage = false;

    public MessageModel(string source, string content, int durationSeconds, bool isSavedMessage = true, bool isEndMessage = false)
    {
        if (source == "PM") source = ProjectManagerName;
        if (source.StartsWith("Business")) source = BusinessExpertName;

        Source = source;
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
