using Hangfire;
using Microsoft.AspNetCore.Mvc.Versioning;
using Microsoft.EntityFrameworkCore;
using Serilog;
using Studi.Api.Core.Exceptions.Middleware;
using Studi.Api.Core.Exceptions.Services;
using Studi.Api.Core.Security.Dependencyinjection;
using Studi.Api.Core.Services.MemoryCache;
using Studi.Api.Core.Swagger;
using Studi.Api.Lms.Messenger;
using Studi.Api.Lms.Messenger.Data.DataContext;
using Studi.Api.Lms.Messenger.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.Messenger.Utils.Middleware;
using System.Globalization;

var builder = WebApplication.CreateBuilder(args);
var config = builder.Configuration;
var services = builder.Services;

services.AddLocalization(options => options.ResourcesPath = "Localization");

// Add multi-langague support for localized errors with error code
services.AddHandleExceptionService(typeof(ErrorCode).Assembly.FullName!);

builder.Host.UseSerilog((ctx, lc) => lc.ReadFrom.Configuration(ctx.Configuration));

// Configure DataContext
services.AddDatabaseConfiguration(config);

// Add Swagger UI
services.AddStudiSwaggerConfiguration();

// Add CORS
services.AddSettingsCors(config);

// Add IoC container services
services.SetIocContainerDependencies(config);

builder.Services.AddApiVersioning(options =>
{
    options.DefaultApiVersion = new Microsoft.AspNetCore.Mvc.ApiVersion(1, 0);
    options.AssumeDefaultVersionWhenUnspecified = true;
    options.ReportApiVersions = true;
    options.ApiVersionReader = ApiVersionReader.Combine(
        new UrlSegmentApiVersionReader());
});

builder.Services.AddVersionedApiExplorer(setup =>
{
    setup.GroupNameFormat = "'v'VVV";
    setup.SubstituteApiVersionInUrl = true;
});

// Add memory cache
services.AddStudiMemoryCache(a => a.CacheExpirationTimeInMinutes = 1);

// Configure migration
services.AddMigrationConfiguration(config);

var app = builder.Build();

// Update database upon start
using (var scope = app.Services.CreateScope())
{
    var messengerDataContext = scope.ServiceProvider.GetRequiredService<MessengerDbContext>();
    messengerDataContext.Database.Migrate();
}

app.UseStudiSwaggerConfiguration();

app.UseHttpsRedirection();

app.UseCors();

app.UseApiVersioning();

// Localization options
var supportedCultures = new List<CultureInfo>
{
    new CultureInfo("fr-FR"),
    new CultureInfo("en-GB")
}.Select(ci => ci.Name).ToArray();

var localizationOptions = new RequestLocalizationOptions()
                            .SetDefaultCulture(supportedCultures.First())
                            .AddSupportedCultures(supportedCultures)
                            .AddSupportedUICultures(supportedCultures);
localizationOptions.ApplyCurrentCultureToResponseHeaders = true;

app.UseRequestLocalization(localizationOptions);

// Add exceptions handling middleware : handle error by code exceptions, and generic exeptions using ExceptionHandlingService
app.UseStudiExceptionHandler();

app.UseStudiSecurity();

app.UseCheckParamsAgainstLmsTokenMiddleware();

#if DEBUG
app.UseHangfireDashboard();
#endif

app.MapControllers();

app.Run();

app.Logger.LogInformation("Application up and running");