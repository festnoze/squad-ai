using Microsoft.AspNetCore.Components.Authorization;
using PoAssistant.Front.Data;

namespace PoAssistant.Front.Services;
public interface ISimpleAuthenticationStateProvider
{
    Task<AuthenticationState> GetAuthenticationStateAsync(string username);
    void MarkUserAsAuthenticated(string username);
    void MarkUserAsLoggedOut(string username);
}