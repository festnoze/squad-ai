using System.Text.Json.Serialization;

public class CreateNewConversationRequestModel
{
    [JsonPropertyName("user_id")]
    public Guid UserId { get; set; }

    [JsonPropertyName("messages")]
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
