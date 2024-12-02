namespace Studi.AI.Chatbot.Front.Services;

public interface INavigationService
{
    void NavigateToLoginPage(bool forceLoad = false);
    void NavigateToPoPage(bool forceLoad = false);
    void NavigateToSignUpPage(bool forceLoad = false);
}