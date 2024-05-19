using Microsoft.Extensions.DependencyInjection;
using Studi.Api.Core.Services.DependencyInjection;

namespace Studi.Api.Lms.Messenger.Application
{
    /// <summary>
    /// Extension class for adding controller-related services to the IServiceCollection.
    /// </summary>
    public static class ServiceCollectionControllerExtension
    {
        /// <summary>
        /// Adds controller services to the IServiceCollection.
        /// </summary>
        /// <param name="services">The IServiceCollection to which services are added.</param>
        /// <returns>The modified IServiceCollection with added controller services.</returns>
        public static IServiceCollection AddControllerServices(this IServiceCollection services)
        {
            return services.AddServices(System.Reflection.Assembly.GetExecutingAssembly());
        }
    }
}
