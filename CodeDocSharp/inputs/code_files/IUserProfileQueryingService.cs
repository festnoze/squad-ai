using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;

namespace Studi.Api.Lms.User.Application.Interfaces
{
    public interface IUserProfileQueryi
    /// <summary>
    /// Get the payment reliability factor for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile information needs to be retrieved.</param>
    /// <returns>Returns the payment reliability factor for the specified user.</returns>
ngService
    {

        Task<string> GetPaymentReliabilityAsy
    /// <summary>
    /// Retrieve user details along with their personal information.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose profile information is to be retrieved.</param>
    /// <returns>Returns a user profile with personal information asynchronously.</returns>
nc(int userId);

        Task<UserModel> GetUserWithPersonalInfosAsy
    /// <summary>
    /// Retrieve basic information about a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether to load additional options related to the school.</param>
    /// <returns>Returns a user profile with basic information.</returns>
nc(int userId);

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOp
    /// <summary>
    /// Retrieve the public information of a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns the user's public information asynchronously.</returns>
tions = false);

        Task<UserModel> GetUserWithPublicInfoAsync(int userId,
    /// <summary>
    /// Retrieve available school options associated with a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school related to the user's profile information being retrieved.</param>
    /// <returns>Returns available school options for the specified user.</returns>
 int schoolId);

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId,
    /// <summary>
    /// Retrieve a list of professional experiences associated with a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information is being retrieved.</param>
    /// <returns>Returns a list of the user's professional experiences.</returns>
 int schoolId);

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsy
    /// <summary>
    /// Retrieve the profile review date for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile information is to be retrieved.</param>
    /// <returns>Returns the profile review date for the specified user asynchronously.</returns>
nc(int userId);

        Task<DateTime?> GetUserProfileReviewDateAsy
    /// <summary>
    /// Retrieve the most recent study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information is being retrieved.</param>
    /// <returns>Returns the user's latest study information.</returns>
nc(int userId);

        Task<StudyModel?> GetUserLastStudyInfosAsy
    /// <summary>
    /// Retrieve a list of contract types related to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types for professional experiences.</returns>
nc(int userId);

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExpe
    /// <summary>
    /// Retrieve details on training that a specified user has undertaken.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school to which the user is affiliated.</param>
    /// <returns>Returns a list of training details for the specified user.</returns>
riencesAsync();
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId,
    /// <summary>
    /// Retrieve notifications for a specified user within a specific school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile information is to be retrieved.</param>
    /// <param name="schoolId">The identifier of the school associated with the user to specify the context of the profile information retrieval.</param>
    /// <returns>Returns user notifications in the specified school context.</returns>
 int schoolId);

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId,
    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <returns>Returns the user's time zone as a string.</returns>
 int schoolId);

        Task<string> GetUserTimeZoneAsy
    /// <summary>
    /// Retrieve configuration information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a task with the user's configuration details.</returns>
nc(int userId);

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId,
    /// <summary>
    /// Retrieve the most recent session information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user's profile information.</param>
    /// <returns>Returns the latest session information for the specified user and school.</returns>
 int schoolId);

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId,
    /// <summary>
    /// Retrieve the date of the first connection for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is to be retrieved.</param>
    /// <returns>Returns the user's first connection date.</returns>
 int schoolId);

        Task<DateTime?> GetUserFirstConnectionDateAsy
    /// <summary>
    /// Get the URL of a user's avatar if it exists.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose profile information is being retrieved.</param>
    /// <returns>Returns the URL of the user's avatar.</returns>
nc(int userId);

        Task<string> GetAvatarUrlAsy
    /// <summary>
    /// Check if a user exists by their email.
    /// </summary>
    /// <param name="email">The email address used to retrieve the user profile information.</param>
    /// <returns>Returns a boolean indicating if a user exists by email.</returns>
nc(int userId);

        Task<bool> ExistUserByEmailAsync
    /// <summary>
    /// Check the existence of a user in the database based on their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudo (or username) of the user whose profile information is to be retrieved in the ExistUserByPseudoAsync method.</param>
    /// <returns>Returns a boolean indicating the existence of a user by pseudonym.</returns>
(string email);

        Task<bool> ExistUserByPseudoAsync(
    /// <summary>
    /// Generate a pseudo-random value given specific parameters.
    /// </summary>
    /// <param name="firstName">The first name of the user to retrieve profile information for.</param>
    /// <param name="lastName">The last name of the user to retrieve profile information for.</param>
    /// <returns>Returns a pseudo-random value based on the provided user information.</returns>
string pseudo);

        Task<string> GeneratePseudoAsync(string firstName, st
    /// <summary>
    /// Count the number of profiles in the dataset.
    /// </summary>
    /// <param name="filtersCompositions">An optional collection of filter compositions used to specify filtering criteria for retrieving user profile information. Defaults to null.</param>
    /// <returns>Returns the total count of profiles matching the specified filters in the dataset.</returns>
ring lastName);

        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompos
    /// <summary>
    /// Retrieve user profiles.
    /// </summary>
    /// <param name="skip">The number of records to skip for pagination.</param>
    /// <param name="take">The number of records to take for pagination.</param>
    /// <param name="filtersCompositions">The collection of filters to apply for retrieving the user profiles, can be null.</param>
    /// <param name="sort">The sorting criteria to apply for retrieving the user profiles, can be null.</param>
    /// <returns>Returns a task with a list of user profiles.</returns>
itions = null);

        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort
    /// <summary>
    /// Retrieve user profile information.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for which the profile information is to be retrieved. It is an integer value.</param>
    /// <returns>Returns a user profile object.</returns>
? sort = null);

        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}