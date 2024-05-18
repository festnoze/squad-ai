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
    /// Check the validity of a specified user's ID and retrieve their payment reliability status.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose payment reliability status is to be checked.</param>
    /// <returns>Returns a user's payment reliability status.</returns>

        Task<string> GetPaymentReliabilityAsync(int userId);

    /// <summary>
    /// Retrieve detailed personal information for a specified user and ensure the data is not null, returning the verified personal information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose personal information is to be retrieved. It ensures that the correct user's data is fetched.</param>
    /// <returns>Returns verified personal details of a specified user.</returns>

        Task<UserModel> GetUserWithPersonalInfosAsync(int userId);

    /// <summary>
    /// Retrieve basic information for a specified user and verify the existence of user data before associating additional information.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose basic information is being retrieved.</param>
    /// <param name="schoolId">The identifier for the school to which the user is associated.</param>
    /// <param name="loadSchoolOptions">A boolean flag indicating whether additional options associated with the school should be loaded. Default is false.</param>
    /// <returns>Returns basic user information with verification and optional school data.</returns>

        Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false);

    /// <summary>
    /// Retrieve the public information of a user, ensuring the user exists, then verify if there are school options for the user in a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user. This parameter is used to retrieve and verify the public information of the user ensuring they exist.</param>
    /// <param name="schoolId">The unique identifier of the school. This parameter is used to check if there are school options available for the user in the specified school.</param>
    /// <returns>Returns the user's public info and school options asynchronously.</returns>

        Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve school options for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. This parameter is used to specify the user for whom the school options need to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school. This parameter is used to specify the school options related to the provided school ID.</param>
    /// <returns>Returns available school options for the specified user and school.</returns>

        Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId);

    /// <summary>
    /// Retrieve professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user whose professional experiences are to be retrieved. This should be an integer.</param>
    /// <returns>Returns a list of user's professional experiences.</returns>

        Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId);

    /// <summary>
    /// Retrieve the review date of the user profile for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date is to be retrieved.</param>
    /// <returns>Returns the review date of the user's profile.</returns>

        Task<DateTime?> GetUserProfileReviewDateAsync(int userId);

    /// <summary>
    /// Retrieve the most recent study information for a specific user.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose most recent study information is being retrieved.</param>
    /// <returns>Returns the latest study information of the specified user.</returns>

        Task<StudyModel?> GetUserLastStudyInfosAsync(int userId);

    /// <summary>
    /// Retrieve a list of contract types applicable to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types for professional experiences.</returns>

        Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync();

    /// <summary>
    /// Retrieve a list of existing training models for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose training models are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a list of the user's training models.</returns>
        Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the notification settings for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose notification settings are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school to which the user belongs.</param>
    /// <returns>Returns a list of user's notification settings for the specified school.</returns>

        Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the time zone information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose time zone information needs to be retrieved.</param>
    /// <returns>Returns the user's time zone information asynchronously.</returns>

        Task<string> GetUserTimeZoneAsync(int userId);

    /// <summary>
    /// Retrieve configuration information for a specified user and school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose configuration information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school associated with the user.</param>
    /// <returns>Returns a task with user's school-specific configuration details.</returns>

        Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the latest session information for a specific user in a designated school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user for whom the latest session information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school where the session information is being fetched.</param>
    /// <returns>Returns the latest session details for the specified user in a given school.</returns>

        Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId);

    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">An integer representing the unique identifier of the user whose first connection date is to be retrieved.</param>
    /// <returns>Returns the user's first connection date as an asynchronous task.</returns>

        Task<DateTime?> GetUserFirstConnectionDateAsync(int userId);

    /// <summary>
    /// Retrieve the avatar URL for a specified user, returning a default URL if no specific URL is found or if the found URL is invalid.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the avatar URL is to be retrieved.</param>
    /// <returns>Returns the avatar URL for the specified user.</returns>

        Task<string> GetAvatarUrlAsync(int userId);

    /// <summary>
    /// Check if a user exists by a specified email address.
    /// </summary>
    /// <param name="email">The email address of the user to check. This parameter is required to identify which user's existence needs to be verified.</param>
    /// <returns>Returns a boolean indicating if the user exists by the given email address.</returns>

        Task<bool> ExistUserByEmailAsync(string email);

    /// <summary>
    /// Check the existence of a user by their pseudo.
    /// </summary>
    /// <param name="pseudo">The pseudo of the user whose existence is being checked in the method ExistUserByPseudoAsync.</param>
    /// <returns>Returns a boolean indicating if a user exists by their pseudo.</returns>

        Task<bool> ExistUserByPseudoAsync(string pseudo);

    /// <summary>
    /// Generate a pseudo name by sending a query with the specified first and last names.
    /// </summary>
    /// <param name="firstName">The first name to be used in generating a pseudo name.</param>
    /// <param name="lastName">The last name to be used in generating a pseudo name.</param>
    /// <returns>Returns the generated pseudo name based on the given first and last names.</returns>

        Task<string> GeneratePseudoAsync(string firstName, string lastName);

    /// <summary>
    /// Count the number of user profiles, applying specified filtering conditions.
    /// </summary>
    /// <param name="filtersCompositions">Optional. A collection of filter compositions to apply when counting user profiles. If no filters are provided, the count will cover all profiles.</param>
    /// <returns>Returns the total count of user profiles matching the specified filters.</returns>

        Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null);

    /// <summary>
    /// Retrieve user profiles based on pagination and filtering criteria, and map associated civility information.
    /// </summary>
    /// <param name="skip">The number of records to skip in the pagination. Used for retrieving the next set of records.</param>
    /// <param name="take">The number of records to take in the pagination. This controls the size of the data set retrieved.</param>
    /// <param name="filtersCompositions">A collection of filters to apply to the data retrieval. These filters help in narrowing down the data based on certain criteria.</param>
    /// <param name="sort">The sorting criteria for ordering the user profiles. It allows the data to be sorted based on specific fields.</param>
    /// <returns>Returns a list of user profiles with associated civility information.</returns>

        Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null);

    /// <summary>
    /// Retrieve the user profile along with the associated civility information if available.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile is to be retrieved.</param>
    /// <returns>Returns the user profile with optional civility details.</returns>

        Task<IUserProfileRAto> GetUserProfileAsync(int userId);
    }
}