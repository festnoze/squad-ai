using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;
using Microsoft.Extensions.Options;
using Studi.AI.Chatbot.Front.Client;
using Studi.AI.Chatbot.Front.Models;
using System.Net;

namespace Studi.AI.Chatbot.Front.Pages;

public partial class Index : ComponentBase
{
    [Inject]
    public IOptions<ChatbotSettings> ChatbotSettings { get; set; }

    private bool showInputMessageAtBottom => ChatbotSettings.Value.ShowInputMessageAtBottom;
    private bool showOngoingMessageInConversation => ChatbotSettings.Value.ShowOngoingMessageInConversation;
    private bool showEmptyOngoingMessageInConversation => ChatbotSettings.Value.ShowEmptyOngoingMessageInConversation;
    private bool doLoginOnStartup => ChatbotSettings.Value.DoLoginOnStartup;

    //
    private string? userName = null;
    private string popupClass = "visible";
    private ConversationModel conversation = null!;
    private string newMessageContent = string.Empty;
    private bool disableConversationModification = false;
    private ElementReference textAreaElement;
    private bool isWaitingForLLM = true;
    private bool isLastMessageEditable => conversationService.IsLastMessageEditable();
    private bool isMenuOpen = false;
    private bool showMessageEmptyError = false;
    private bool showApiErrorNotification = false;
    private string apiErrorNotificationMessage = "Erreur de communication avec l'API du chatbot";
    private bool isLoginModalVisible { get; set; } = false;
    private Modal modal { get; set; } = new Modal();
    private DeviceInfoModel? deviceInfo = null;
    private string? IP = null;


    protected override async Task OnInitializedAsync()
    {
        conversation = conversationService.GetConversation();
        isWaitingForLLM = conversationService.IsWaitingForLLM();

        conversationService.OnConversationChanged += ReloadConversation;
        conversationService.ApiCommunicationErrorNotification += ShowApiCommunicationError;
    }

    public async Task OpenPopup()
    {
        popupClass = "visible";
        await InvokeAsync(StateHasChanged);
    }

    private async Task ClosePopup()
    {
        popupClass = "hidden";
        await InvokeAsync(StateHasChanged);
    }

    private async Task LoginModalIsVisibleChangedAsync(bool isVisible)
    {
        isLoginModalVisible = isVisible;
        await InvokeAsync(StateHasChanged);
    }

    private async Task RetrieveInputTextAreaValueAsync()
    {
        if (!disableConversationModification)
        {
            conversation!.Last().ChangeContent(await JSRuntime.InvokeAsync<string>("getElementValue", "editingMessageTextarea"));
        }
    }

    private async Task SetDeviceInfoAndIPAsync()
    {
        if (deviceInfo is null)
        {
            deviceInfo = await JSRuntime.InvokeAsync<DeviceInfoModel>("getDeviceInfo");
            conversationService.SetDeviceInfo(deviceInfo);
        }
        if (IP is null)
        {
            //IP = await Http.GetFromJsonAsync<string>("proxy/get-ip");
            IP = await JSRuntime.InvokeAsync<string>("getIp");
            conversationService.SetIP(IP!);
        }
    }

    private async Task EmptyAndDisableInputTextAreaAsync()
    {
        await JSRuntime.InvokeAsync<string>("setElementValue", "editingMessageTextarea", "");
        await JSRuntime.InvokeAsync<string>("setDisabledValueToElement", "editingMessageTextarea", true);
        await JSRuntime.InvokeAsync<string>("setDisabledValueToElement", "sendEditingMessageButton", true);
    }

    private async Task EnableInputTextAreaAsync()
    {
        await JSRuntime.InvokeAsync<string>("setDisabledValueToElement", "editingMessageTextarea", false);  
        await JSRuntime.InvokeAsync<string>("setDisabledValueToElement", "sendEditingMessageButton", false);        
    }

    private async Task HandleEditMessageKeyDown(KeyboardEventArgs e)
    {
        if (e.Key == "Enter" && !e.CtrlKey && !e.ShiftKey)
        {
            await JSRuntime.InvokeVoidAsync("event.preventDefault"); // Prevent default behavior to avoid adding a newline
            await RetrieveInputTextAreaValueAsync();
            await SendMessage();
        }
        else if (e.Key == "Enter" && e.CtrlKey)
        {
            await RetrieveInputTextAreaValueAsync(); 
            await JSRuntime.InvokeAsync<string>("setElementValue", "editingMessageTextarea", conversation!.Last().Content + "\n");
        }
        else
        {
            await RetrieveInputTextAreaValueAsync();
            await JSRuntime.InvokeVoidAsync("scrollChatContainerToBottom");
        }
    }

    private bool ShouldDisplayMessage(MessageModel message)
    {
        return !message.IsLastMessageOfConversation || !showInputMessageAtBottom || (showOngoingMessageInConversation && (!message.IsEmpty || showEmptyOngoingMessageInConversation));
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            //await JSRuntime.InvokeVoidAsync("autoResizeTextarea", "editingMessageTextarea");
            await JSRuntime.InvokeVoidAsync("scrollChatContainerToBottom");

        }
        await SetDeviceInfoAndIPAsync();

        if (doLoginOnStartup && userName is null && !isLoginModalVisible)
        {
            userName = await JSRuntime.InvokeAsync<string>("blazorExtensions.ReadStorage", "userName");
            conversationService.SetCurrentUser(userName);
            var authState = await authenticationStateProvider.GetAuthenticationStateAsync(userName);
            if (!authState.User.Identity!.IsAuthenticated)
            {
                isLoginModalVisible = true;
                await InvokeAsync(StateHasChanged);
            }
        }

        await base.OnAfterRenderAsync(firstRender);
    }

    private bool DisplayEditingButtons(MessageModel message)
    {
        return isLastMessageEditable && !showInputMessageAtBottom && !isWaitingForLLM && message.IsLastMessageOfConversation && !message.IsSavedMessage;
    }

    private bool DisplayLoader(MessageModel message)
    {
        return !isLastMessageEditable && isWaitingForLLM && message.IsStreaming;
    }

    private bool IsEditableLastMessage(MessageModel message)
    {
        return isLastMessageEditable && message.IsLastMessageOfConversation && message.IsFromUser && !message.IsSavedMessage;
    }

    private async Task SendMessage()
    {
        await RetrieveInputTextAreaValueAsync();
        disableConversationModification = true;
        conversation!.Last().ChangeContent(conversation!.Last().Content.Trim());

        if (isLastMessageEditable && string.IsNullOrWhiteSpace(conversation!.Last().Content))
        {
            ShowEmptyMessageError();
            return;
        }

        //TODO: to remove TMP: special command to create vector DB
        if (conversation!.Last().Content == "db")
        {
            await conversationService.CreateVectorDbAsync();
        }

        isWaitingForLLM = true;
        await EmptyAndDisableInputTextAreaAsync();

        string? userName = "not defined";
                
        try
        {
            await conversationService.AnswerUserQueryAsync(userName);
        }
        catch (NewConversationsQuotaOverloadException)
        {
            apiErrorNotificationMessage = "Vous avez atteind le nombre maximum de conversations quotidiennes. Veuillez attendre demain avec de réessayer.";
            ShowApiCommunicationError();
        }
        catch (RequestsPerConversationQuotaOverloadException)
        {
            apiErrorNotificationMessage = "Vous avez atteind le nombre maximum d'échanges par conversation.\nVous pouvez recommencer une nouvelle conversation.";
            ShowApiCommunicationError();
        }
        catch (HttpRequestException ex)
        {
            apiErrorNotificationMessage = $"Erreur HTTP '{ex.StatusCode?.ToString() ?? "N.C"}' lors de l'appel au service du chatbot";
            ShowApiCommunicationError();
        }
        catch (Exception ex)
        {
            apiErrorNotificationMessage = $"Erreur lors de l'appel au service du chatbot: {ex.Message}";
            ShowApiCommunicationError();
        }

        await EnableInputTextAreaAsync();
        disableConversationModification = false;

        await InvokeAsync(StateHasChanged);
    }

    private async void ReloadConversation()
    {
        conversation = conversationService.GetConversation();
        isWaitingForLLM = conversationService.IsWaitingForLLM();
        await InvokeAsync(StateHasChanged);
    }

    private void ShowEmptyMessageError()
    {
        showMessageEmptyError = true;
        var task = Task.Delay(8000).ContinueWith(t =>
        {
            showMessageEmptyError = false;
            InvokeAsync(StateHasChanged);
        });
    }

    private void ShowApiCommunicationError()
    {
        showApiErrorNotification = true;
        var task = Task.Delay(8000).ContinueWith(t =>
        {
            showApiErrorNotification = false;
            apiErrorNotificationMessage = "";
            InvokeAsync(StateHasChanged);
        });
    }

    private void ToggleMenu()
    {
        isMenuOpen = !isMenuOpen;
    }

    public void Dispose()
    {
        conversationService.OnConversationChanged -= ReloadConversation;
        conversationService.ApiCommunicationErrorNotification -= ShowApiCommunicationError;
    }
}
