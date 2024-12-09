﻿using System.Text;
using System.Text.Json;
using Studi.AI.Chatbot.Front.Client;
using Studi.AI.Chatbot.Front.Helpers;

public class ChatbotAPIClient
{
    private readonly HttpClient _httpClient;
    private readonly string _baseUrl;

    public ChatbotAPIClient(string baseUrl)
    {
        _baseUrl = baseUrl.TrimEnd('/');
        _httpClient = new HttpClient();
    }

    /// <summary>
    /// Get a new conversation ID from the server.
    /// </summary>
    /// <param name="userName"></param>
    /// <returns></returns>
    /// <exception cref="Exception"></exception>
    public async Task<Guid> GetNewConversationIdAsync(string? userName)
    {
        string endpoint = $"{_baseUrl}/rag/inference/query/create";
        string jsonPayload = JsonSerializer.Serialize(userName);
        var request = new HttpRequestMessage(HttpMethod.Get, endpoint)
        {
            Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json")
        };

        using (HttpResponseMessage response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead))
        {
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadAsStringAsync();

            // Deserialize the JSON object into a class
            var conversationResponse = JsonSerializer.Deserialize<CreateConversationResponseModel>(result);

            if (conversationResponse == null || conversationResponse.Id == Guid.Empty)
            {
                throw new Exception($"Invalid response from client to {nameof(GetNewConversationIdAsync)} endpoint.");
            }

            return conversationResponse.Id;
        }
    }

    /// <summary>
    /// Ask a question to the chatbot and get the answer as streaming.
    /// </summary>
    /// <param name="userQueryAskingRequestModel"></param>
    /// <returns></returns>
    public async IAsyncEnumerable<string> GetQueryRagAnswerStreamingAsync(UserQueryAskingRequestModel userQueryAskingRequestModel)
    {
        string endpoint = $"{_baseUrl}/rag/inference/query/stream";
        string jsonPayload = JsonSerializer.Serialize(userQueryAskingRequestModel);
        var request = new HttpRequestMessage(HttpMethod.Post, endpoint)
        {
            Content = new StringContent(jsonPayload, Encoding.UTF8, "application/json")
        };

        using (HttpResponseMessage response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead))
        {
            response.EnsureSuccessStatusCode();

            using (var stream = await response.Content.ReadAsStreamAsync())
            using (var reader = new StreamReader(stream))
            {
                while (!reader.EndOfStream)
                {
                    var word = await reader.ReadWordAsync();
                    if (!string.IsNullOrEmpty(word))
                        yield return word;
                }
            }
        }
    }

    /// <summary>
    /// Create the vector database 
    /// </summary>
    /// <returns></returns>
    /// <exception cref="Exception"></exception>
    public async Task<bool> CreateVectorDatabaseAsync()
    {
        string endpoint = $"{_baseUrl}/data/vector_db";

        using (var request = new HttpRequestMessage(HttpMethod.Post, endpoint))
        {
            using (HttpResponseMessage response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead))
            {
                response.EnsureSuccessStatusCode();

                var result = await response.Content.ReadAsStringAsync();

                if (string.IsNullOrWhiteSpace(result) || !bool.TryParse(result, out var success))
                {
                    throw new Exception($"Invalid response from client to {nameof(CreateVectorDatabaseAsync)} endpoint.");
                }

                return success;
            }
        }
    }
}