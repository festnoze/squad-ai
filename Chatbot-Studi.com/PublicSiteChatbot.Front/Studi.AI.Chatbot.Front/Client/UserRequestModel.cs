namespace Studi.AI.Chatbot.Front.Client;

using System.Text.Json.Serialization;

public class UserRequestModel
{
    [JsonPropertyName("user_id")]
    public Guid? UserId { get; set; }

    [JsonPropertyName("user_name")]
    public string UserName { get; set; } = "";

    [JsonPropertyName("IP")]
    public string IP { get; set; } = "";

    [JsonPropertyName("device_info")]
    public string DeviceInfo { get; set; } = "";
}
