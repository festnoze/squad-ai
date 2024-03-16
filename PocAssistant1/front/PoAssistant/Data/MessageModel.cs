using System.Text.Json.Serialization;

namespace PoAssistant.Front.Data;

public record MessageModel
{
    [JsonPropertyName("source")]
    public string Source { get; init; }

    [JsonPropertyName("content")]
    public string Content { get; set; }

    public bool IsSender => Source == "MOE";

    public bool IsLastThreadMessage { get; private set; } = false;
    public bool SetAsLastThreadMessage () => IsLastThreadMessage = true;

    public MessageModel(string source, string content)
    {
        Source = source;
        Content = content;
    }
}
