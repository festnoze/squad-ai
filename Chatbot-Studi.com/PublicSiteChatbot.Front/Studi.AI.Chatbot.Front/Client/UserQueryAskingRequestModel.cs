namespace Studi.AI.Chatbot.Front.Client;

using System.Text.Json.Serialization;

public class UserQueryAskingRequestModel
{
    [JsonPropertyName("conversation_id")]
    public Guid ConversationId { get; set; }

    [JsonPropertyName("user_query_content")]
    public string UserQueryContent { get; set; } = "";

    [JsonPropertyName("display_waiting_message")]
    public bool DisplayWaitingMessage { get; set; } = true;

}
