﻿using Newtonsoft.Json;

namespace PoAssistant.Front.Client;

using System.Text.Json.Serialization;

public class ConversationRequestModel
{
    [JsonPropertyName("messages")]
    public List<MessageRequestModel> Messages { get; set; } = new List<MessageRequestModel>();
}

public class MessageRequestModel
{
    [JsonPropertyName("role")]
    public string Source { get; set; } = "";

    [JsonPropertyName("content")]
    public string Content { get; set; } = "";

    [JsonPropertyName("duration_seconds")]
    public float DurationSeconds { get; set; } = 0;
}