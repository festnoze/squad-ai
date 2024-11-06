namespace PoAssistant.Front.Services;

using Microsoft.AspNetCore.Components.Authorization;
using PoAssistant.Front.Data;
using PoAssistant.Front.Infrastructure;
using System.Security.Claims;
using System.Threading.Tasks;

public class SimpleAuthenticationStateProvider : ISimpleAuthenticationStateProvider
{
    private readonly IUserRepository _userRepository;

    public static List<User> ConnectedUsers { get; private set; } = new List<User>();

    public SimpleAuthenticationStateProvider(IUserRepository userRepository)
    {
        this._userRepository = userRepository;
    }

    public Task<AuthenticationState> GetAuthenticationStateAsync(string username)
    {
        var identity = new ClaimsIdentity();
        var currentUser = ConnectedUsers.Find(u => u.Username == username);
        if (currentUser != null)
        {
            identity = new ClaimsIdentity(new[]
                { new Claim(ClaimTypes.Name, currentUser.Username) }, 
                "simple_auth");
        }

        var user = new ClaimsPrincipal(identity);
        return Task.FromResult(new AuthenticationState(user));
    }

    public void MarkUserAsAuthenticated(string username)
    {
        var currentUser = _userRepository.GetUserByUsername(username);
        if (currentUser != null)
        {
            var existingUser = ConnectedUsers.Find(u => u.Username == username);
            if (existingUser != null)
                ConnectedUsers.Remove(existingUser);
            ConnectedUsers.Add(currentUser);
        }
    }

    public void MarkUserAsLoggedOut(string username)
    {
        var currentUser = ConnectedUsers.Find(u => u.Username == username);
        if (currentUser != null)
            ConnectedUsers.Remove(currentUser);
    }
}


