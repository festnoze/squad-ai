namespace Studi.Api.Lms.Application.Services;

using MediatR;
using Studi.Api.Core.Exceptions.ErrorCodesLocalization.Base;
using Studi.Api.Core.Exceptions.Guards;
using Studi.Api.Core.Services.DependencyInjection.Attributes;
using Studi.Api.Lms.User.Application.Interfaces;
using Studi.Api.Lms.User.Domain.Aggregates.User.Models;
using Studi.Api.Lms.User.Domain.Aggregates.User.Queries;
using Studi.Api.Lms.User.Localization.Error.GeneratedClasses;
using Studi.Api.Lms.User.Common.ITOs;
using Studi.Api.Lms.User.Application.Services.CustomWebResource;
using Studi.Api.Core.Pagination.Filter;
using Studi.Api.Lms.User.Application.Decorators;
using Studi.Api.Lms.User.Application.Tools;
using Studi.Api.Lms.User.Application.Mapper;
using Studi.Api.Core.Pagination.Sort;
using Studi.Api.Lms.User.Application.ATOs;
using Studi.Api.Lms.User.Application.Services.Civility;
using Studi.Api.Lms.User.Common.RepositoriesInterfaces;

[ScopedService(typeof(IUserProfileQueryingService))]
public class UserProfileQueryingService : IUserProfileQueryingService
{
    private readonly IMediator _mediator;
    private readonly ICustomWebResourceService _customWebResource;
    private readonly ICivilityService _civilityService;
    private readonly IUserRepository _userRepository;


    /// <summary>
    /// Initialize the necessary dependencies for querying user profiles with non-null mediator, custom web resource, civility service, and user repository components.
    /// </summary>
    /// <param name="mediator">An instance of IMediator interface, required for handling asynchronous messaging and communication between different components.</param>
    /// <param name="customWebResource">An ICustomWebResourceService that provides functionalities to work with custom web resources required for user profile querying.</param>
    /// <param name="civilityService">A service implementing ICivilityService, used for managing and retrieving civility-related data for user profiles.</param>
    /// <param name="userRepository">An IUserRepository instance responsible for accessing and manipulating user data in the database.</param>
    public UserProfileQueryingService(IMediator mediator, ICustomWebResourceService customWebResource, ICivilityService civilityService, IUserRepository userRepository)
    {
        _mediator = mediator ?? throw new ArgumentNullException();
        _customWebResource = customWebResource ?? throw new ArgumentNullException();
        _civilityService = civilityService ?? throw new ArgumentNullException();
        _userRepository = userRepository;
    }


    /// <summary>
    /// Retrieve payment reliability information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier for a user which is an integer. This parameter is used to specify the user whose payment reliability information is to be retrieved.</param>
    /// <returns>Returns a user's payment reliability score asynchronously.</returns>
    public async Task<string?> GetPaymentReliabilityAsync(int userId)
    {
        Guard.Against.NegativeOrZero(userId, ErrorCode.Api.Lms.User.DataValidation.Common.UserId.NegativeOrZero);
        return await _userRepository.GetPaymentReliabilityAsync(userId);
    }



    /// <summary>
    /// Retrieve basic information for a specified user.
    /// </summary>
    /// <param name="userId">The identifier of the user whose basic information is being retrieved.</param>
    /// <param name="schoolId">The identifier of the school associated with the user.</param>
    /// <param name="loadSchoolOptions">Specifies whether to load additional school options. Defaults to false.</param>
    /// <returns>Returns a user's basic information asynchronously.</returns>
    public async Task<UserModel> GetUserWithBasicInfoAsync(int userId, int schoolId, bool loadSchoolOptions = false)
    {
        var user = await _mediator.Send(new UserBaseQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.User.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        var userBasicInfoIto = await _mediator.Send(new UserBasicInfoQuery(userId));
        user!.SetBasicInfoInformations(BasicInfoModel.CreateExisting(userBasicInfoIto!));

        if (loadSchoolOptions)
        {
            var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
            Guard.Against.Null(userSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve basic public information for a specified user, then determine if the user has specific school options.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom to retrieve basic public information in the method 'GetUserWithPublicInfoAsync'.</param>
    /// <param name="schoolId">The identifier of the school to determine if the specified user has specific school options in the method 'GetUserWithPublicInfoAsync'.</param>
    /// <returns>Returns basic public user info and school options availability.</returns>
    public async Task<UserModel> GetUserWithPublicInfoAsync(int userId, int schoolId)
    {
        var user = await _mediator.Send(new UserPublicInfoQuery(userId));
        Guard.Against.Null(user, ErrorCode.Api.Lms.User.DataValidation.Query.PublicInfo.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString()); //TODO Localize

        var userSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        if (userSchoolOptions != null)
        {
            user!.SetUserSchoolOptions(UserSchoolOptionsModel.CreateExisting(userSchoolOptions!));

            var userScoresItos = await _mediator.Send(new UserScoresQuery(userId, schoolId));
            user!.SetUserScoresModel(userScoresItos is null ? null : UserScoresModel.CreateExisting(userScoresItos!));

            var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
            Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);
            user!.SetTrainings(TrainingModel.CreateExistingList(userTrainingsItos!));
        }

        return user!;
    }


    /// <summary>
    /// Retrieve user information including their course registrations, filtering by a specified user ID and school ID.
    /// </summary>
    /// <param name="userId">The ID of the user whose information and course registrations are being retrieved.</param>
    /// <param name="schoolId">The ID of the school to filter the course registrations for the specified user.</param>
    /// <returns>Returns user details and filtered course registrations.</returns>
    //[Obsolete("replaced by Trainings")]
    //public async Task<UserModel> GetUserWithCoursesRegistrationsAsync(int userId, int schoolId)
    //{
    //    var user = await _mediator.Send(new UserCoursesRegistrationsQuery(userId, schoolId));
    //    return user.UserCoursesRegistrations.First().ToIto();
    //}


    /// <summary>
    /// Retrieve personal information for a specified user and ensure the data is not null, returning the information if available.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom personal information is being retrieved. This is an integer value.</param>
    /// <returns>Returns a user's personal information as a non-null object.</returns>
    public async Task<UserModel> GetUserWithPersonalInfosAsync(int userId)
    {
        var userWPersonalInfos = await _mediator.Send(new UserPersonnalInformationsQuery(userId));
        Guard.Against.Null(userWPersonalInfos, ErrorCode.Api.Lms.User.DataValidation.Query.PersonnalInfos.NotFoundByUserId, ErrorKind.BadRequest, userId.ToString());

        return userWPersonalInfos!;
    }


    /// <summary>
    /// Retrieve available school options for a specific user, given the user's ID and associated school ID.
    /// </summary>
    /// <param name="userId">The unique identifier for the user. It is used to specify which user's school options are being retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school. It specifies the school context for the user whose options are being retrieved.</param>
    /// <returns>Returns user's available school options.</returns>
    public async Task<UserSchoolOptionsModel> GetUserSchoolOptions(int userId, int schoolId)
    {
        var userWSchoolOptions = await _mediator.Send(new UserSchoolOptionsQuery(userId, schoolId));
        Guard.Against.Null(userWSchoolOptions, ErrorCode.Api.Lms.User.DataValidation.Query.SchoolOptions.NotFoundByUserIdAndSchoolId, ErrorKind.BadRequest, userId.ToString(), schoolId.ToString());

        return UserSchoolOptionsModel.CreateExisting(userWSchoolOptions!);
    }


    /// <summary>
    /// Retrieve professional experiences for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the professional experiences are to be retrieved.</param>
    /// <returns>Returns a list of the specified user's professional experiences.</returns>
    public async Task<IEnumerable<ProfessionalExperienceModel>> GetUserProfessionalExperiencesAsync(int userId)
    {
        return (await _mediator.Send(new UserProfessionalExperiencesQuery(userId))).ProfessionalExperiences;
    }


    /// <summary>
    /// Retrieve the review date of a specified user's profile.
    /// </summary>
    /// <param name="userId">The ID of the user whose profile review date is to be retrieved.</param>
    /// <returns>Returns the review date of a specified user's profile as an asynchronous task.</returns>
    public async Task<DateTime?> GetUserProfileReviewDateAsync(int userId)
    {
        return await _mediator.Send(new UserProfileReviewDateQuery(userId));
    }


    /// <summary>
    /// Retrieve the most recent study information for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose most recent study information is to be retrieved.</param>
    /// <returns>Returns the latest study details for a specified user.</returns>
    public async Task<StudyModel?> GetUserLastStudyInfosAsync(int userId)
    {
        return await _mediator.Send(new UserLastStudyInfosQuery(userId));
    }


    /// <summary>
    /// Retrieve a list of contract types relevant to professional experiences.
    /// </summary>
    /// <returns>Returns a list of contract types for professional experiences.</returns>
    public async Task<IEnumerable<ContractTypeIto>> GetContractTypesListForProfessionalExperiencesAsync()
    {
        return await _mediator.Send(new AllContractTypesForProfessionalExperiencesQuery());
    }


    /// <summary>
    /// Retrieve the training records for a specific user associated with a particular school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose training records are to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school with which the user is associated.</param>
    /// <returns>Returns a list of a user's training records for a specified school.</returns>
    public async Task<IEnumerable<TrainingModel>> GetUserTrainingsAsync(int userId, int schoolId)
    {
        var userTrainingsItos = await _mediator.Send(new UserTrainingsQuery(userId, schoolId));
        Guard.Against.Null(userTrainingsItos, ErrorCode.Api.Lms.User.DataValidation.Query.Trainings.NotFoundByUserIdAndSchoolId);

        return TrainingModel.CreateExistingList(userTrainingsItos);
    }


    /// <summary>
    /// Retrieve user notifications based on user ID and school ID.
    /// </summary>
    /// <param name="userId">The ID of the user for whom notifications are being retrieved.</param>
    /// <param name="schoolId">The ID of the school associated with the user's notifications.</param>
    /// <returns>Returns a list of user notifications.</returns>
    public async Task<UserModel> GetUserNotificationsByIdAndSchoolIdAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserNotificationsSettingsQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the time zone for a specified user.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the time zone is to be retrieved.</param>
    /// <returns>Returns the user's time zone as a string.</returns>
    public async Task<string> GetUserTimeZoneAsync(int userId)
    {
        return await _mediator.Send(new UserTimeZoneQuery(userId));
    }


    /// <summary>
    /// Retrieve configuration information for a specific user and school.
    /// </summary>
    /// <param name="userId">The unique identifier of the user for whom the configuration information is being retrieved.</param>
    /// <param name="schoolId">The unique identifier of the school associated with the user for retrieving the configuration information.</param>
    /// <returns>Returns the configuration details for a specified user and school.</returns>
    public async Task<UserConfigInfosIto?> GetUserConfigInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserConfigInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the last session information for a specified user within a specified school.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose last session information is to be retrieved.</param>
    /// <param name="schoolId">The unique identifier for the school where the user's last session information is to be retrieved.</param>
    /// <returns>Returns the user's last session details at the specified school.</returns>
    public async Task<LastSessionInfosModel> GetLastSessionInfosAsync(int userId, int schoolId)
    {
        return await _mediator.Send(new UserLastSessionInfosQuery(userId, schoolId));
    }


    /// <summary>
    /// Retrieve the first connection date for a specified user.
    /// </summary>
    /// <param name="userId">The ID of the user for whom the first connection date is to be retrieved.</param>
    /// <returns>Returns the first connection date of the specified user as a DateTime.</returns>
    public async Task<DateTime?> GetUserFirstConnectionDateAsync(int userId)
    {
        return await _mediator.Send(new UserFirstConnectionDateQuery(userId));
    }


    /// <summary>
    /// Get the avatar URL for a specified user; if the URL is invalid, return a default avatar URL.
    /// </summary>
    /// <param name="userId">The unique identifier for the user whose avatar URL is being requested.</param>
    /// <returns>Returns the user's avatar URL or a default URL if invalid.</returns>
    public async Task<string> GetAvatarUrlAsync(int userId)
    {
        var url = await _mediator.Send(new UserAvatarUrlQuery(userId));

        if (!string.IsNullOrEmpty(url) 
            && !string.IsNullOrWhiteSpace(url))
            return url;

        return _customWebResource.DefaultAvatarUrl;
    }


    /// <summary>
    /// Check if a user exists by email.
    /// </summary>
    /// <param name="email">The email address to check for the user's existence.</param>
    /// <returns>Returns a task with a boolean indicating if the user exists by email.</returns>
    public async Task<bool> ExistUserByEmailAsync(string email)
    {
        return await _mediator.Send(new UserExistByEmailQuery(email));
    }


    /// <summary>
    /// Check if a user exists by their pseudonym.
    /// </summary>
    /// <param name="pseudo">The pseudonym of the user. This parameter is used to identify and check if a user exists by their pseudonym in the 'ExistUserByPseudoAsync' method.</param>
    /// <returns>Returns a boolean indicating user's existence by pseudonym.</returns>
    public async Task<bool> ExistUserByPseudoAsync(string pseudo)
    {
        return await _mediator.Send(new UserExistByPseudoQuery(pseudo));
    }


    /// <summary>
    /// Create a pseudo identifier for a user based on their first and last names.
    /// </summary>
    /// <param name="firstName">The user's given first name used to generate the pseudo identifier.</param>
    /// <param name="lastName">The user's surname used to generate the pseudo identifier.</param>
    /// <returns>Returns a pseudo identifier for the user.</returns>
    public async Task<string> GeneratePseudoAsync(string firstName, string lastName)
    {
        return await _mediator.Send(new UserGeneratePseudoQuery(firstName, lastName));
    }


    /// <summary>
    /// Count the number of user profiles based on specified filter criteria.
    /// </summary>
    /// <param name="filtersCompositions">Optional. A collection of filters to apply to the user profiles. This parameter accepts an IEnumerable of IFiltersComposition of type object and is used to specify the filter criteria for counting the profiles. If not provided, no filters will be applied and the count will include all profiles.</param>
    /// <returns>Returns the count of user profiles matching the specified filters.</returns>
    public async Task<int> CountProfilesAsync(IEnumerable<IFiltersComposition<object>>? filtersCompositions = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);

        return await _mediator.Send(new UserProfilesCountQuery(filtersCompositions));
    }


    /// <summary>
    /// Retrieve the user profiles with specified filters and sorting criteria, transform the filtering and sorting fields, and map civilities to the user profiles.
    /// </summary>
    /// <param name="skip">The number of records to skip, typically used for pagination purposes.</param>
    /// <param name="take">The number of records to take, indicating the size of the result set to return.</param>
    /// <param name="filtersCompositions">Optional parameter for a collection of filter compositions to apply various filters dynamically on the user profiles.</param>
    /// <param name="sort">Optional parameter to define the sorting criteria based on which the user profiles should be ordered.</param>
    /// <returns>Returns a list of user profiles based on applied filters and sorting criteria.</returns>
    public async Task<IEnumerable<IUserProfileRAto>> GetUserProfilesAsync(int skip, int take, IEnumerable<IFiltersComposition<object>>? filtersCompositions = null, ISort? sort = null)
    {
        var fieldNameDecorator = new TransformTextFromMappingDecorator(FilterableFieldMapper.UserPorfileRAtoToRItoDicoMapping);
        PaginationTools.TransformFilterFieldName(filtersCompositions, fieldNameDecorator);
        PaginationTools.TransformSortFieldName(sort, fieldNameDecorator);

        var data = await _mediator.Send(new UserProfilesQuery(skip, take, filtersCompositions, sort));

        if(!data.Any())
            return Enumerable.Empty<IUserProfileRAto>();

        var civilities = this._civilityService.GetCivilities();
        return data.Select(q => ItoToAtoMapper.ToUserProfileRAto(q, civilities.FirstOrDefault(c => c.Name == q.Civility)?.Id));
    }


    /// <summary>
    /// Retrieve the user profile along with corresponding civility data if available.
    /// </summary>
    /// <param name="userId">The unique identifier of the user whose profile is to be retrieved.</param>
    /// <returns>Returns a task with the user's profile and optional civility data.</returns>
    public async Task<IUserProfileRAto> GetUserProfileAsync(int userId)
    {
        var data = await _mediator.Send(new UserProfileQuery(userId));
        var civility = !string.IsNullOrEmpty(data.Civility) ? this._civilityService.GetCivilityByName(data.Civility!) : null;

        return ItoToAtoMapper.ToUserProfileRAto(data, civility?.Id);
    }
}