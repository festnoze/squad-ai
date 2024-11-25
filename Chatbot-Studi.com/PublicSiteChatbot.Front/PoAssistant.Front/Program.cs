using Microsoft.AspNetCore.Components.Authorization;
using PoAssistant.Front.Data;
using PoAssistant.Front.Infrastructure;
using PoAssistant.Front.Services;

var builder = WebApplication.CreateBuilder(args);

// Add strongly type settings
builder.Services.Configure<ApiSettings>(builder.Configuration.GetSection("ApiSettings"));

// Add services to the container.
builder.Services.AddRazorPages();
builder.Services.AddServerSideBlazor();

builder.Services.AddControllers();

builder.Services.AddSingleton<ConversationService>();
builder.Services.AddSingleton<UserStoryService>();
builder.Services.AddScoped<NavigationService>();
builder.Services.AddSingleton<IUserRepository, UserRepository>();
builder.Services.AddSingleton<IExchangeRepository, ExchangeRepository>();
builder.Services.AddScoped<IAuthenticationService, AuthenticationService>();
builder.Services.AddScoped<ISimpleAuthenticationStateProvider, SimpleAuthenticationStateProvider>();


var app = builder.Build();

// Configure the HTTP request pipeline.
if (!app.Environment.IsDevelopment())
{
    app.UseExceptionHandler("/Error");
    // The default HSTS value is 30 days. You may want to change this for production scenarios, see https://aka.ms/aspnetcore-hsts.
    app.UseHsts();
}

app.UseStaticFiles();

app.UseRouting();

app.MapBlazorHub();

app.UsePathBase("/MetierPoExchange");
app.MapFallbackToPage("/_Host");

app.MapControllers(); // Handle proxy API controllers
app.Run();
