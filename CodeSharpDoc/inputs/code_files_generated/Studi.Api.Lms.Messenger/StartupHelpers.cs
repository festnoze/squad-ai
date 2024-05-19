using Hangfire;
using Hangfire.MemoryStorage;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.Extensions.Options;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Security.Dependencyinjection;
using Studi.Api.Core.Services.DependencyInjection;
using Studi.Api.Lms.Messenger.Application;
using Studi.Api.Lms.Messenger.Controllers.Contact.ListingSelector;
using Studi.Api.Lms.Messenger.Controllers.Conversation.ListingSelector;
using Studi.Api.Lms.Messenger.Controllers.Message.ListingSelector;
using Studi.Api.Lms.Messenger.Data.DataContext;
using Studi.Api.Lms.Messenger.Data.Migrations.Configuration;
using Studi.Api.Lms.Messenger.Infra.Data;
using Studi.Api.Lms.Messenger.Infra.External.Data;
using Studi.Api.Lms.Messenger.Shared.ContactListing;
using Studi.Api.Lms.Messenger.Shared.ConversationListing;
using Studi.Api.Lms.Messenger.Shared.MessageListing;
using Studi.Api.Core.ListingSelector.Filtering.AvailableFilters;
using Studi.Api.Core.ListingSelector.JsonConversion;
using Studi.Api.Core.ListingSelector.Sorting.AvailableSortings;
using Studi.Api.WebSockets.Client;
using Studi.EmailTemplateClient;
using Studi.LmsDatabase.Models;
using System.Reflection;

namespace Studi.Api.Lms.Messenger;

/// <summary>
/// Provides a collection of static helper methods to configure and set up various services for the application.
/// </summary>
public static class StartupHelpers
{
    /// <summary>
    /// Configures and sets up various services for the application and adds them to the IOC container.
    /// </summary>
    /// <param name="services">The IServiceCollection to add the services to.</param>
    /// <param name="config">The configuration manager to retrieve configuration settings.</param>
    public static void SetIocContainerDependencies(this IServiceCollection services, ConfigurationManager config)
    {
        // Add services to the container.
        var apiCoreOptions = Options.Create(new ApiCoreServicesOptions(
                            isUsingCqrsRequestWithMediator: false,
                            isUsingDomainEventsWithMediator: false,
                            isUsingCqrsRequestDataValidation: false));
        services.AddApiCoreServices(apiCoreOptions);
        services.AddApplicationServices();
        services.AddInfrastructureServices();
        services.AddControllerServices();
        services.AddUserInfrastructureServices();
        services.AddScoped<IEmailTemplating>(jwt => new EmailTemplating(config["EmailTemplateUrl"]));
        services.AddControllers().AddNewtonsoftJson(options =>
        {
            var jsonConverterForConversation = new ListingSelectorJsonConverter<IConversationListing>(
                    (Activator.CreateInstance(typeof(AvailableFiltersForConversation)) as IAvailableFilters<IConversationListing>)!,
                    (Activator.CreateInstance(typeof(AvailableSortingsForConversation)) as IAvailableSortings<IConversationListing>)!);

            var jsonConverterForContact = new ListingSelectorJsonConverter<IContactListing>(
                    (Activator.CreateInstance(typeof(AvailableFiltersForContact)) as IAvailableFilters<IContactListing>)!,
                    null);
            var jsonConverterForMessage = new ListingSelectorJsonConverter<IMessageListing>(
                    (Activator.CreateInstance(typeof(AvailableFiltersForMessage)) as IAvailableFilters<IMessageListing>)!,
                    null);

            options.SerializerSettings.Converters.Add(jsonConverterForConversation);
            options.SerializerSettings.Converters.Add(jsonConverterForContact);
            options.SerializerSettings.Converters.Add(jsonConverterForMessage);
        });
        services.AddSwaggerGenNewtonsoftSupport();

        services.AddSwaggerGen(c =>
        {
            var mainProjectXmlFile = $"{Assembly.GetExecutingAssembly().GetName().Name}.xml";
            var mainProjectXmlPath = Path.Combine(AppContext.BaseDirectory, mainProjectXmlFile);

            c.IncludeXmlComments(mainProjectXmlPath);

            var nugetPackageXmlPath = Path.Combine(AppContext.BaseDirectory, "Studi.Api.Lms.Messenger.ExchangeDataContract.xml");
            if (File.Exists(nugetPackageXmlPath))
            {
                c.IncludeXmlComments(nugetPackageXmlPath);
            }
        });

        services.AddEndpointsApiExplorer();

        Application.Notifications.ServiceCollectionApplicationExtension.AddApplicationServices(services);

        var unifiedApiUri = config.GetValue<string>("UnifiedApiUri");
        services.AddStudiSecurity(unifiedApiUri);
        services.AddWebSocketsServiceByClient(webSocketsInstancesOption: options => config.Bind("WebsocketsConfiguration", options));

        services.AddHangfire(config => config.UseMemoryStorage());
        services.AddHangfireServer();
    }

    /// <summary>
    /// Configures the application's database context with the provided connection string and other settings.
    /// </summary>
    /// <param name="services">The IServiceCollection to add the database configuration to.</param>
    /// <param name="configuration">The configuration to retrieve the database connection settings.</param>
    public static void AddDatabaseConfiguration(this IServiceCollection services, IConfiguration configuration)
    {
        var connectionString = configuration.GetConnectionString("LMSConnection");
        var commandTimeOut = (int)TimeSpan.Parse(configuration["CommandTimeout"]).TotalSeconds;

        // Set CS for Messenger datacontext and set request timeout
        services.AddDbContext<MessengerDbContext>(options =>
            options.UseSqlServer(connectionString,
            optionsBuilder =>
            {
                optionsBuilder.CommandTimeout(commandTimeOut);
                optionsBuilder.MigrationsHistoryTable(
                    HistoryRepository.DefaultTableName, Data.DataContext.Helper.MessengerSchema);
            }));

        // Set CS for LMS datacontext and set request timeout
        services.AddDbContext<StudiLmsContext>(options =>
            options.UseSqlServer(connectionString,
            optionsBuilder =>
            {
                optionsBuilder.CommandTimeout(commandTimeOut);
            }));
    }

    /// <summary>
    /// Configures the application's database migration settings based on the provided configuration.
    /// </summary>
    /// <param name="services">The IServiceCollection to add the migration configuration to.</param>
    /// <param name="configuration">The configuration to retrieve the database migration settings.</param>
    public static void AddMigrationConfiguration(this IServiceCollection services, IConfiguration configuration)
    {
        // Set 'DatabaseKind' migration property
        var databaseKind = configuration["DatabaseKind"];

        if (Enum.TryParse(databaseKind, out DatabaseKindEnum currentDatabaseKind))
            MigrationConfiguration.DatabaseKind = currentDatabaseKind;
        else
            MigrationConfiguration.DatabaseKind = DatabaseKindEnum.NEW_DB;

        Console.WriteLine($"<<<< DatabaseKind = {MigrationConfiguration.DatabaseKind} >>>>");

        // Set 'DatabaseEnvironment' migration property
        var databaseEnvironment = configuration["DatabaseEnvironment"];

        if (Enum.TryParse(databaseEnvironment, out DatabaseEnvironmentEnum currentDatabaseEnvironment))
            MigrationConfiguration.DatabaseEnvironment = currentDatabaseEnvironment;
        else
            Guard.Throw($"Unhandled database environment entitled '{databaseEnvironment}'. Fix the value setted for 'DatabaseEnvironment' property in the application settings.");

        Console.WriteLine($"---/ DatabaseEnvironment = {MigrationConfiguration.DatabaseEnvironment} /---");
    }

    /// <summary>
    /// Configures CORS (Cross-Origin Resource Sharing) settings for the application.
    /// </summary>
    /// <param name="services">The IServiceCollection to add the CORS settings to.</param>
    /// <param name="config">The configuration manager to retrieve CORS settings.</param>
    public static void AddSettingsCors(this IServiceCollection services, ConfigurationManager config)
    {
        services.AddCors(options =>
        {
            var allowedCorsOrigins = config.GetSection("AllowedCorsOrigins").Get<string[]>();
            options.AddDefaultPolicy(
                builder =>
                {
                    builder
                    .WithOrigins(allowedCorsOrigins)
                    .AllowAnyHeader()
                    .AllowAnyMethod()
                    .AllowCredentials();
                });
        });
    }
}