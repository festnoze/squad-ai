using PoAssistant.Front.Data;
using PoAssistant.Front.Helpers;
using PoAssistant.Front.Infrastructure;
using PoAssistant.Front.Client;
using Microsoft.Extensions.Options;

namespace PoAssistant.Front.Services;

public class ConversationService : IConversationService
{
    private ChatbotAPIClient _chatbotApiClient;
    private readonly IExchangeRepository _exchangeRepository;
    private ConversationModel? conversation = null;
    public event Action? OnConversationChanged = null;
    private bool isWaitingForLLM = false;
    private readonly string _apiHostUri;

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

    private string? username = null;
    public void SetCurrentUser(string userName)
    {
        this.username = userName;
    }

    public bool IsLastMessageEditable()
    {
        return conversation!.IsLastMessageFromUser && !conversation!.Last().IsSavedMessage;
    }

    public bool IsWaitingForLLM() => isWaitingForLLM;

    public async Task<Guid> ApiCallGetNewConversationIdAsync(string? userName)
    {
        return await this._chatbotApiClient.GetNewConversationIdAsync(userName);
    }

    public async Task ApiCallAnswerUserQueryAsync(ConversationModel conversation)
    {
        if (!conversation?.Any() ?? true)
            return;

        conversation!.Last().ChangeContent(conversation!.Last().Content.Trim());
        if (string.IsNullOrWhiteSpace(conversation!.Last().Content))
            return;
        conversation!.Last().IsSavedMessage = true;
        //SaveConversation();

        var conversationRequestModel = conversation!.ToRequestModel();
        try
        {
            this.AddNewMessage(isSaved: false, isStreaming: true);

            await foreach (var chunk in this._chatbotApiClient.GetQueryRagAnswerStreamingAsync(conversationRequestModel))
            {
                this.DisplayStreamMessage(chunk);
            }

            this.EndsStreamMessage();
            this.AddNewMessage(isSaved: false, isStreaming: false);
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

    public void DisplayStreamMessage(string? messageChunk)
    {
        // New lines are a specific pattern to allow spliting words and avoid win/mac issue over the streaming
        if (!string.IsNullOrEmpty(messageChunk))
        {
            isWaitingForLLM = true;
            conversation!.Last().AddContent(messageChunk.Replace(StreamHelper.NewLineForStream, StreamHelper.WindowsNewLine));
            OnConversationChanged?.Invoke();
        }
    }

    public void EndsStreamMessage()
    {
        conversation!.Last().IsStreaming = false;
        conversation!.Last().IsSavedMessage = true;
    }

    public void LoadConversationByName(string exchangeNameTruncated, bool truncatedExchangeName = false)
    {
        _isExchangesLoaded = false;
        conversation = _exchangeRepository.LoadUserExchange(username!, exchangeNameTruncated, truncatedExchangeName);
        if (conversation is null)
            throw new InvalidOperationException($"Cannot load the Conversation as the exchange is not found for user: {username}");

        OnConversationChanged?.Invoke();
    }

    public void SaveConversation()
    {
        if (username is null)
            username = "defaultUser";

        var newConversation = _exchangeRepository.SaveUserExchange(username, conversation!);
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
