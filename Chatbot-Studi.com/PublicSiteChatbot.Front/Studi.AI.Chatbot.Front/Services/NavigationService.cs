namespace Studi.AI.Chatbot.Front.Services;

using Microsoft.AspNetCore.Components;

public class NavigationService : INavigationService
{
    private NavigationManager _navigationManager;

    public NavigationService(NavigationManager navigationManager)
    {
        _navigationManager = navigationManager;
    }

    public void NavigateToPoPage(bool forceLoad = false)
    {
        _navigationManager.NavigateTo("po", forceLoad);
    }

    public void NavigateToSignUpPage(bool forceLoad = false)
    {
        _navigationManager.NavigateTo("signup", forceLoad);
    }

    public void NavigateToLoginPage(bool forceLoad = false)
    {
        _navigationManager.NavigateTo("login", forceLoad);
    }
}
