using Microsoft.AspNetCore.Components;
using Microsoft.AspNetCore.Components.Web;
using Microsoft.JSInterop;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Pages;

public partial class Index : ComponentBase
{
    private string? userName = null;
    private ConversationModel messages = null!;
    private string newMessageContent = string.Empty;
    private ElementReference textAreaElement;
    private bool isWaitingForLLM = true;
    private bool isLastMessageEditable => conversationService.IsLastMessageEditable();
    private bool showBottomInputMessage = true;
    private bool showOngoingMessageInConversation = false;
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
        conversationService.ApiCommunicationErrorNotification += HandleApiCommunicationErrorNotification;
    }

    private async Task LoginModalIsVisibleChangedAsync(bool isVisible)
    {
        IsLoginModalVisible = isVisible;
        await InvokeAsync(StateHasChanged);
    }

    private async Task RetrieveInputTextAreaValueAsync()
    {
        messages!.Last().Content = await JSRuntime.InvokeAsync<string>("getElementValue", "editingMessageTextarea");
    }

    private async Task EmptyAndDisableInputTextAreaAsync()
    {
        await JSRuntime.InvokeAsync<string>("setElementValue", "editingMessageTextarea", "");
        await JSRuntime.InvokeAsync<string>("setDisabledValueToElement", "editingMessageTextarea", true);
    }

    private async Task EnableInputTextAreaAsync()
    {
        await JSRuntime.InvokeAsync<string>("setDisabledValueToElement", "editingMessageTextarea", false);        
    }

    private async Task HandleEditMessageKeyDown(KeyboardEventArgs e)
    {
        if (e.Key == "Enter" && !e.CtrlKey && !e.ShiftKey)
        {
            await JSRuntime.InvokeVoidAsync("event.preventDefault"); // Prevent default behavior to avoid adding a newline
            await RetrieveInputTextAreaValueAsync();
            await SendMessage();
        }
        else
        {
            await RetrieveInputTextAreaValueAsync();
        }
    }

    protected override async Task OnAfterRenderAsync(bool firstRender)
    {
        if (firstRender)
        {
            await AutosizeEditingTextAreaAsync();
        }

        // Desactivated Login TODO: make optionnal through env. config.
        IsLoginModalVisible = false;
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
        return !isLastMessageEditable && !showBottomInputMessage && !isWaitingForLLM && message.IsLastConversationMessage && !message.IsSavedMessage;
    }

    private bool DisplayLoader(MessageModel message)
    {
        return !isLastMessageEditable && isWaitingForLLM && message.IsStreaming;
    }

    private bool IsEditableLastMessage(MessageModel message)
    {
        return isLastMessageEditable && message.IsLastConversationMessage && message.IsFromUser && !message.IsSavedMessage;
    }

    private void ShowMessageEmptyError()
    {
        showMessageEmptyError = true;
        var task = Task.Delay(8000).ContinueWith(t =>
        {
            showMessageEmptyError = false;
            InvokeAsync(StateHasChanged);
        });
    }

    private void ToggleMenu()
    {
        isMenuOpen = !isMenuOpen;
    }

    private async Task SendMessage()
    {
        await RetrieveInputTextAreaValueAsync();
        messages!.Last().Content = messages!.Last().Content.Trim();
        if (isLastMessageEditable && string.IsNullOrEmpty(messages!.Last().Content))
        {
            ShowMessageEmptyError();
            return;
        }

        isWaitingForLLM = true;
        await EmptyAndDisableInputTextAreaAsync();

        await conversationService.InvokeRagApiOnUserQueryAsync(messages!);

        await EnableInputTextAreaAsync();
        await InvokeAsync(StateHasChanged);
    }

    private async void ReloadConversation()
    {
        messages = conversationService.GetConversation();
        isWaitingForLLM = conversationService.IsWaitingForLLM();
        await InvokeAsync(StateHasChanged);
    }

    private async void HandleApiCommunicationErrorNotification()
    {
        showApiCommunicationErrorNotification = true;
        await InvokeAsync(StateHasChanged);

        await Task.Delay(5000);

        showApiCommunicationErrorNotification = false;
        await InvokeAsync(StateHasChanged);
    }

    public void Dispose()
    {
        conversationService.OnConversationChanged -= ReloadConversation;
        conversationService.ApiCommunicationErrorNotification -= HandleApiCommunicationErrorNotification;
    }
}
