using Microsoft.AspNetCore.Components.Authorization;
using PoAssistant.Front.Data;
using PoAssistant.Front.Infrastructure;
using System.Security.Claims;

namespace PoAssistant.Front.Services;

public interface IAuthenticationService
{
    Task<bool> SignUpAsync(string userName, string userPassword);
    Task<bool> LoginAsync(string userName, string userPassword);
}

public class AuthenticationService : IAuthenticationService
{
    private readonly IUserRepository _userRepository;
    private readonly ISimpleAuthenticationStateProvider _authenticationStateProvider;

    public AuthenticationService(IUserRepository userRepository, ISimpleAuthenticationStateProvider authenticationStateProvider)
    {
        this._userRepository = userRepository;
        this._authenticationStateProvider = authenticationStateProvider;
    }

    public async Task<bool> SignUpAsync(string userName, string userPassword)
    {
        if (!CheckPasswordValidity(userName, userPassword))
            return false;

        if (_userRepository.CheckUserExists(userName))
            return false;

        _userRepository.AddUser(new User(userName, userPassword));

        return await LoginAsync(userName, userPassword);
    }

    private static bool CheckPasswordValidity(string username, string password)
    {
        if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password) || password.Length <= 4)
            return false;

        return true;
    }

    public async Task<bool> LoginAsync(string userName, string userPassword)
    {
        if (!_userRepository.CheckUserExists(userName))
            return false;
        if(!_userRepository.ValidateUserPassword(userName, userPassword))
            return false;

        _authenticationStateProvider.MarkUserAsAuthenticated(userName);
        return true;
    }
}

