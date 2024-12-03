using Studi.AI.Chatbot.Front.Data;
using Studi.AI.Chatbot.Front.Helpers;
using Studi.AI.Chatbot.Front.Infrastructure;
using Studi.AI.Chatbot.Front.Client;
using Microsoft.Extensions.Options;

namespace Studi.AI.Chatbot.Front.Services;

public class ConversationService : IConversationService
{
    private ChatbotAPIClient _chatbotApiClient;
    private string? userName = null;
    private ConversationModel? conversation = null;
    public event Action? OnConversationChanged = null;
    private bool isWaitingForLLM = false;
    private readonly string _apiHostUri;
    private readonly IExchangeRepository _exchangeRepository;

    public ConversationService(IExchangeRepository exchangesRepository, IOptions<ApiSettings> apiSettings)
    {
        _exchangeRepository = exchangesRepository;
        _apiHostUri = apiSettings.Value.ApiHostUri;
        _chatbotApiClient = new ChatbotAPIClient(_apiHostUri);
        InitializeConversation();
    }

    private void InitializeConversation()
    {
        if (conversation is null || !conversation.Any())
        {
            var startMessage = "Bonjour,\nJe suis Studia, votre assistant virtuel.\nComment puis-je vous aider ?";

            conversation = new ConversationModel();
            conversation.AddMessage(MessageModel.AiRole, startMessage, 0, true, false);
            conversation.AddMessage(MessageModel.UserRole, string.Empty, 0, false, false);
            _isExchangesLoaded = true;
            isWaitingForLLM = false;
        }
    }

    public ConversationModel GetConversation()
    {
        return conversation!;
    }

    public void SetCurrentUser(string userName)
    {
        this.userName = userName;
    }

    public bool IsLastMessageEditable()
    {
        return conversation!.IsLastMessageFromUser && !conversation!.Last().IsSavedMessage;
    }

    public bool IsWaitingForLLM() => isWaitingForLLM;

    public async Task GetAnswerToUserLastQueryAsync()
    {
        if (!conversation?.Any() ?? true)
            return;

        conversation!.Last().ChangeContent(conversation!.Last().Content.Trim());
        if (string.IsNullOrWhiteSpace(conversation!.Last().Content))
            return;
        if (!conversation!.IsLastMessageFromUser)
            return;

        if (conversation!.Id is null)
        {
            conversation!.Id = await this._chatbotApiClient.GetNewConversationIdAsync(userName);
        }

        conversation!.Last().IsSavedMessage = true;
        //SaveConversation();

        try
        {
            var userQueryAskingRequestModel = conversation!.ToUserQueryAskingRequestModel();
            this.AddNewMessage(isSaved: false, isStreaming: true); // Add a new message where the answer will be streamed

            var queryAnsweringStream = this._chatbotApiClient.GetQueryRagAnswerStreamingAsync(userQueryAskingRequestModel);

            await foreach (var chunk in queryAnsweringStream)
            {
                this.AddStreamToLastMessage(chunk);
            }
            this.EndsMessageStream();

            this.AddNewMessage(isSaved: false, isStreaming: false); // Add a new message for the next user query
        }
        catch (Exception e)
        {
            this.NotifyForApiCommunicationError(e.Message);
        }
    }

    public event Action? ApiCommunicationErrorNotification;

    protected virtual void NotifyForApiCommunicationError(string errorMessage)
    {
        ApiCommunicationErrorNotification?.Invoke();
    }

    public void AddNewMessage(bool isSaved = false, bool isStreaming = true)
    {
        if (conversation is null)
            conversation = new ConversationModel();

        if (!conversation?.Any() ?? true)
            throw new Exception($"{nameof(AddNewMessage)} cannot be used on a null or empty conversation.");

        var role = conversation!.Last().IsFromAI ? MessageModel.UserRole : MessageModel.AiRole;
        var newMessage = new MessageModel(role, string.Empty, -1, isSaved, isStreaming);
        conversation!.AddMessage(newMessage);

        isWaitingForLLM = isStreaming;
        OnConversationChanged?.Invoke();
    }

    public void AddStreamToLastMessage(string? messageChunk)
    {
        // New lines have a specific pattern to allow spliting words and avoid win/mac issue over the streaming
        if (!string.IsNullOrEmpty(messageChunk))
        {
            isWaitingForLLM = true;
            messageChunk = messageChunk.Replace(StreamHelper.NewLineForStream, StreamHelper.WindowsNewLine);

            if (messageChunk.Contains(StreamHelper.EraseAllStream))
                conversation!.Last().ChangeContent(string.Empty);
            else if (messageChunk.Contains(StreamHelper.EraseSinglePreviousChunk))
                conversation!.Last().RemoveLastWord();
            else
                conversation!.Last().AddContent(messageChunk);

            OnConversationChanged?.Invoke();
        }
    }

    public void EndsMessageStream()
    {
        conversation!.Last().IsStreaming = false;
        conversation!.Last().IsSavedMessage = true;
    }

    public void LoadConversationByName(string exchangeNameTruncated, bool truncatedExchangeName = false)
    {
        _isExchangesLoaded = false;
        conversation = _exchangeRepository.LoadUserExchange(userName!, exchangeNameTruncated, truncatedExchangeName);
        if (conversation is null)
            throw new InvalidOperationException($"Cannot load the Conversation as the exchange is not found for user: {userName}");

        OnConversationChanged?.Invoke();
    }

    public void SaveConversation()
    {
        if (userName is null)
            userName = "defaultUser";

        var newConversation = _exchangeRepository.SaveUserExchange(userName, conversation!);
        if (newConversation)
            _isExchangesLoaded = false;
    }

    public void DeleteCurrentConversation()
    {
        _isExchangesLoaded = false;
        conversation = null;
        InitializeConversation();
        OnConversationChanged?.Invoke();
    }

    private bool _isExchangesLoaded = false;
    public bool IsExchangesLoaded => _isExchangesLoaded;

    public void MarkConversationAsLoaded()
    {
        _isExchangesLoaded = true;
    }

    public void Dispose()
    {
    }
}
