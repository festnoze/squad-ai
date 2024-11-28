using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Pages;

public partial class Index : ComponentBase
{
    private bool showBottomInputMessage = false;
    private bool showOngoingMessageInConversation = true;
    private bool showEmptyOngoingMessageInConversation = true;
    private string? userName = null;
    private ConversationModel messages = null!;
    private string newMessageContent = string.Empty;
    private bool disableConversationModification = false;
    private ElementReference textAreaElement;
    private bool isWaitingForLLM = true;
    private bool isLastMessageEditable => conversationService.IsLastMessageEditable();
    private bool isMenuOpen = false;
    private bool showMessageEmptyError = false;
    private bool showApiCommunicationErrorNotification = false;
    private bool IsLoginModalVisible { get; set; }
    private Modal modal { get; set; } = new Modal();

    protected override async Task OnInitializedAsync()
    {
        messages = conversationService.GetConversation();
        isWaitingForLLM = conversationService.IsWaitingForLLM();
        conversationService.OnConversationChanged += ReloadConversation;
        conversationService.ApiCommunicationErrorNotification += ShowApiCommunicationError;
    }

    private async Task LoginModalIsVisibleChangedAsync(bool isVisible)
    {
        IsLoginModalVisible = isVisible;
        await InvokeAsync(StateHasChanged);
    }

    private async Task RetrieveInputTextAreaValueAsync()
    {
        if (!disableConversationModification)
        {
            messages!.Last().Content = await JSRuntime.InvokeAsync<string>("getElementValue", "editingMessageTextarea");
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
            await JSRuntime.InvokeAsync<string>("setElementValue", "editingMessageTextarea", messages!.Last().Content + "\n");
        }
        else
        {
            await RetrieveInputTextAreaValueAsync();
        }
    }

    private bool ShouldDisplayMessage(MessageModel message)
    {
        return !message.IsLastMessageOfConversation || !showBottomInputMessage || (showOngoingMessageInConversation && (!message.IsEmpty || showEmptyOngoingMessageInConversation));
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            await AutosizeEditingTextAreaAsync();
        }

        IsLoginModalVisible = false;

        // Desactivated Login TODO: make optionnal through env. config.
        // if (!IsLoginModalVisible)
        // {
        //     userName = await JSRuntime.InvokeAsync<string>("blazorExtensions.ReadStorage", "userName");
        //     conversationService.SetCurrentUser(userName);
        //     var authState = await authenticationStateProvider.GetAuthenticationStateAsync(userName);
        //     if (!authState.User.Identity!.IsAuthenticated)
        //     {
        //         IsLoginModalVisible = true;
        //         await InvokeAsync(StateHasChanged);
        //     }
        // }

        await base.OnAfterRenderAsync(firstRender);
    }

    private async Task AutosizeEditingTextAreaAsync()
    {
        await JSRuntime.InvokeVoidAsync("autoResizeTextarea", "editingMessageTextarea");
    }

    private bool DisplayEditingButtons(MessageModel message)
    {
        return isLastMessageEditable && !showBottomInputMessage && !isWaitingForLLM && message.IsLastMessageOfConversation && !message.IsSavedMessage;
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
        messages!.Last().Content = messages!.Last().Content.Trim();
        if (isLastMessageEditable && string.IsNullOrEmpty(messages!.Last().Content))
        {
            ShowEmptyMessageError();
            return;
        }

        isWaitingForLLM = true;
        await EmptyAndDisableInputTextAreaAsync();

        await conversationService.InvokeRagApiOnUserQueryAsync(messages!);

        await EnableInputTextAreaAsync();
        disableConversationModification = false;
        await InvokeAsync(StateHasChanged);
    }

    private async void ReloadConversation()
    {
        messages = conversationService.GetConversation();
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
        showApiCommunicationErrorNotification = true;
        //await InvokeAsync(StateHasChanged);
        var task = Task.Delay(8000).ContinueWith(t =>
        {
            showApiCommunicationErrorNotification = false;
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
