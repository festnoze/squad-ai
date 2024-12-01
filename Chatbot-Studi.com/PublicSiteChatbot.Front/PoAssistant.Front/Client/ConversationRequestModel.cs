using Newtonsoft.Json;

namespace PoAssistant.Front.Client;

using System.Text.Json.Serialization;

public class ConversationRequestModel
{
    [JsonPropertyName("conversation")]
    public List<MessageRequestModel> Messages { get; set; } = new List<MessageRequestModel>();
}

public class MessageRequestModel
{
    [JsonPropertyName("role")]
    public string Role { get; set; } = "";

    [JsonPropertyName("content")]
    public string Content { get; set; } = "";

    [JsonPropertyName("duration_seconds")]
    public float DurationSeconds { get; set; } = 0.0f;
}
