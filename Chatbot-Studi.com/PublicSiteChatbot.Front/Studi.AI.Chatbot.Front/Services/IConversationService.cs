﻿using Studi.AI.Chatbot.Front.Data;

namespace Studi.AI.Chatbot.Front.Services;
public interface IConversationService : IDisposable
{
    bool IsExchangesLoaded { get; }

    event Action? ApiCommunicationErrorNotification;
    event Action? OnConversationChanged;

    Task GetAnswerToUserLastQueryAsync();
    void AddNewMessage(bool isSaved = false, bool isStreaming = true);
    void DeleteCurrentConversation();
    void AddStreamToLastMessage(string? messageChunk);
    void EndsMessageStream();
    ConversationModel GetConversation();
    bool IsLastMessageEditable();
    bool IsWaitingForLLM();
    void LoadConversationByName(string exchangeNameTruncated, bool truncatedExchangeName = false);
    void MarkConversationAsLoaded();
    void SaveConversation();
    void SetCurrentUser(string userName);
}