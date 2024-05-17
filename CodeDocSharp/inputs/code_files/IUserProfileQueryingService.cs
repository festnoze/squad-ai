using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileQueryingService
    {

        /// <summary>
        /// Get payment reliability
        /// </summary>
        /// <param name="userId"></param>
        /// <returns></returns>
        Task<string> GetPaymentReliabilityAsync(int userId);

        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

        Task<string> GetUserTimeZoneAsync(int userId);

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

        /// <summary>
        /// Get avatar url
        /// </summary>
        /// <param name="userId">User Id</param>
        /// <returns></returns>
        Task<string> GetAvatarUrlAsync(int userId);

        /// <summary>
        /// Exist user by email
        /// </summary>
        /// <param name="email">Email</param>
        /// <returns></returns>
        Task<bool> ExistUserByEmailAsync(string email);

        /// <summary>
        /// Exist user by pseudo
        /// </summary>
        /// <param name="pseudo">Pseudo</param>
        /// <returns></returns>
        Task<bool> ExistUserByPseudoAsync(string pseudo);

        /// <summary>
        /// Generate pseudo
        /// </summary>
        /// <param name="firstName">First name</param>
        /// <param name="lastName">Last name</param>
        /// <returns></returns>
        Task<string> GeneratePseudoAsync(string firstName, string lastName);

        /// <summary>
        /// Count profiles
        /// </summary>
        /// <param name="filtersCompositions">Filters compositions</param>
        /// <returns></returns>
        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

        /// <summary>
        /// Get suer profiles
        /// </summary>
        /// <param name="skip">Skip</param>
        /// <param name="take">Take</param>
        /// <param name="filtersCompositions">Filters compositions</param>
        /// <param name="sort">Sort</param>
        /// <returns></returns>
        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

        /// <summary>
        /// Get user profile
        /// </summary>
        /// <param name="userId">User id</param>
        /// <returns></returns>
        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}