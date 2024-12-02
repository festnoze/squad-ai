using Microsoft.AspNetCore.Components.Authorization;
using Studi.AI.Chatbot.Front.Data;

namespace Studi.AI.Chatbot.Front.Services;
public interface ISimpleAuthenticationStateProvider
{
    Task<AuthenticationState> GetAuthenticationStateAsync(string username);
    void MarkUserAsAuthenticated(string username);
    void MarkUserAsLoggedOut(string username);
}