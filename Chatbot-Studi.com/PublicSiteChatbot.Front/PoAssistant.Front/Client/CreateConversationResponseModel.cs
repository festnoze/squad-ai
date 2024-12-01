using System.Text.Json.Serialization;

public class CreateConversationResponseModel
{

    [JsonPropertyName("id")]
    public Guid Id { get; set; }
}