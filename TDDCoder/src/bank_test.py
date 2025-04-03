from dataclasses import dataclass
from enum import Enum
from typing import Union
import uuid
from uuid import UUID
import pytest
from decimal import Decimal, getcontext, ROUND_DOWN

class TestClass:
    def setup_method(self):
        self.services = BankingServices()
    
    def teardown_method(self):
        pass

    def test_create_account_should_work(self):
        # Given a user named Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        
        # When he creates an account
        account_id = self.services.create_account(user_first_name, user_last_name)

        # Then the account should be created successfully
        accounts = self.services.get_all_accounts_ids()
        assert account_id in accounts, "created account should be in all accounts"

    def test_get_account_by_user_should_work(self):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)
        
        # When he retrieves the account by user name
        retrieved_account = self.services.get_account_by_user_name(user_first_name, user_last_name)

        # Then the retrieved account should match the searched one
        assert retrieved_account.id == account_id, "retrieved account should match created account"
        assert retrieved_account.first_name == user_first_name, "retrieved account first name should match"
        assert retrieved_account.last_name == user_last_name, "retrieved account last name should match"

    def test_account_balance_should_be_zero_when_created(self):
        # Given a user named Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        
        # When he creates an account
        account_id = self.services.create_account(user_first_name, user_last_name)

        # Then the account balance should be zero
        account = self.services.get_account_by_id(account_id)
        assert account is not None, "account should be found by its id"
        assert account.get_balance() == 0.0, "account balance should be zero when created"

    def test_get_account_by_user_id_should_work(self):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)
        
        # When he retrieves the account by ID
        retrieved_account = self.services.get_account_by_id(account_id)

        # Then the retrieved account should match the searched one
        assert retrieved_account.id == account_id, "retrieved account should match created account"
        assert retrieved_account.first_name == user_first_name, "retrieved account first name should match"
        assert retrieved_account.last_name == user_last_name, "retrieved account last name should match"

    @pytest.mark.parametrize("initial_balance, deposit_amount, awaited_final_balance", 
        [
            (0.0, 100.0, 100.0),
            (50.0, 50.0, 100.0),
            (100.51, 200.4, 300.91),
            (500000.09, 500.9, 500500.99), #amounts with decimals values can raise precision errors with Decimal
            (0.01, 0.011, 0.02), # amounts with 3 decimals are rounded to 2 decimals 
            (10000000000.0, 10000000000.0, 20000000000.0),
        ]
    )
    def test_deposit_to_account_should_work(self, initial_balance, deposit_amount, awaited_final_balance):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)
        if initial_balance != 0:
            self.services.deposit_to_account(account_id, initial_balance)
        
        # When he deposits money into the account    
        self.services.deposit_to_account(account_id, deposit_amount)

        # Then the account balance should reflect the deposit
        account = self.services.get_account_by_id(account_id)
        assert account is not None, "account should be found by its id"
        assert account.get_balance() == Helper.to_currency(initial_balance) + Helper.to_currency(deposit_amount), "account balance should match the deposit amount (with 2 decimals)"
        assert account.get_balance() == Helper.to_currency(awaited_final_balance), "account balance should match the awaited final balance"

    @pytest.mark.parametrize("initial_balance, deposit_amount, exception_type, awaited_error",
        [
            (0.0, -100.0, ValueError, "Deposit amount must be positive"),
            (100.0, -50.0, ValueError, "Deposit amount must be positive"),
            (100.0, 0.0, ValueError, "Deposit amount must be positive"),
        ]
    )
    def test_deposit_to_account_should_fail(self, initial_balance, deposit_amount, exception_type, awaited_error):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)
        if initial_balance != 0:
            self.services.deposit_to_account(account_id, initial_balance)

        # When he deposits money into the account    
        with pytest.raises(Exception) as ex:
            self.services.deposit_to_account(account_id, deposit_amount)

            # Then the expected exception type and message occurs
            assert isinstance(ex.value, exception_type), f"Expected {exception_type}, but got {type(ex.value)}"
            assert str(ex.value) == awaited_error, f"Expected error message '{awaited_error}', but got '{str(ex.value)}'"

    @pytest.mark.parametrize("initial_balance, withdrawal_amount, awaited_final_balance",
        [
            (50.0, 50.0, 0.0),
            (500000.09, 500.9, 499499.19), #amounts with decimals values can raise precision errors with Decimal
            (0.01, 0.011, 0.0), # amounts with 3 decimals are rounded to 2 decimals 
            (10000000000.0, 10000000000, 0.0),
        ]
    )
    def test_withdrawal_should_work(self, initial_balance, withdrawal_amount, awaited_final_balance):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)        
        if initial_balance != 0:
            self.services.deposit_to_account(account_id, initial_balance)

        # When he withdraws money into the account
        self.services.withdrawal_from_account(account_id, withdrawal_amount)

        # Then the account balance should reflect the deposit
        assert self.services.get_account_balance(account_id) == Helper.to_currency(awaited_final_balance), "account balance should match the deposit amount (with 2 decimals)"

    @pytest.mark.parametrize("initial_balance, withdrawal_amount, exception_type, awaited_error",
        [
            (50.0, -50.0, ValueError, "Withdrawal amount must be positive"),
            (50.0, 0.0, ValueError, "Withdrawal amount must be positive"),
            (0.0, 0.1, ValueError, "Insufficient funds"),
            (50.0, 100.0, ValueError, "Insufficient funds"),
        ]
    )
    def test_withdrawal_should_fail(self, initial_balance, withdrawal_amount, exception_type, awaited_error):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)        
        if initial_balance != 0:
            self.services.deposit_to_account(account_id, initial_balance)

        # When he withdraws money into the account
        with pytest.raises(Exception) as ex:
            self.services.withdrawal_from_account(account_id, withdrawal_amount)

            # Then the expected exception type and message occurs
            assert isinstance(ex.value, exception_type), f"Expected {exception_type}, but got {type(ex.value)}"
            assert str(ex.value) == awaited_error, f"Expected error message '{awaited_error}', but got '{str(ex.value)}'"

    @pytest.mark.parametrize("initial_balance, operations, final_balance", [
        [ 
            0.0,
            [
                {"operation_type": "deposit", "amount": 100.0},
                # {"operation_type": "withdrawal", "amount": 50.0},
                # {"operation_type": "transfer", "amount": 200.0}
            ],
            100.0
        ]
    ])
    def test_get_account_operations_should_work(self, initial_balance: Decimal, operations: list[dict], final_balance: Decimal):
        # Given a created account for user Dave Toe
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)

        if initial_balance != 0:
            self.services.deposit_to_account(account_id, initial_balance)

        for operation in operations:
            if operation["operation_type"] == OperationType.DEPOSIT.value:
                self.services.deposit_to_account(account_id, operation["amount"])
            elif operation["operation_type"] == OperationType.WITHDRAWAL.value:
                self.services.withdrawal_from_account(account_id, operation["amount"])
            elif operation["operation_type"] == OperationType.TRANSFER.value:
                raise NotImplementedError("Transfer operation is not implemented yet")

        # When he retrieves the account operations
        actual_operations = self.services.get_account_operations(account_id)

        # Then the operations should match the expected ones
        assert len(actual_operations) == len(operations), "number of operations should match"
        for operation_dict, actual_operation in zip(operations, actual_operations):
            operation = Operation.from_dict(operation_dict)
            assert operation == actual_operation, "each single retrieved operation should match the expected operation"
        #equals to: assert all([Operation.from_dict(operation)== actual_operation for operation, actual_operation in zip(operations, actual_operations)]), "each single retrieved operations should match"
        assert self.services.get_account_balance(account_id) == Helper.to_currency(final_balance), "account balance should match the final balance" # TODO: Balance to test in a separate test than operations

    def test_get_bank_statement_should_work(self):
        # Given an account with operations
        user_first_name = "Dave"
        user_last_name = "Toe"
        account_id = self.services.create_account(user_first_name, user_last_name)
        self.services.deposit_to_account(account_id, 100.0)
        self.services.withdrawal_from_account(account_id, 50.0)
        self.services.withdrawal_from_account(account_id, 20.0)
        self.services.withdrawal_from_account(account_id, 10.0)
        self.services.deposit_to_account(account_id, 200.0)
        self.services.withdrawal_from_account(account_id, 100.0)
        self.services.withdrawal_from_account(account_id, 50.0)
        
        # When he retrieves the bank statement
        bank_statement = self.services.get_account_bank_statement(account_id)

        # Then the bank statement should reflect the operations
        assert len(bank_statement) != 0, "bank statement shouldn't be empty when operations are performed"
        assert bank_statement == "Bank Statement for Dave Toe account:\n-----------------------------------\nDate           Operation      Amount         \n-----------------------------------\nN.C            deposit        100.00         \nN.C            withdrawal     50.00          \nN.C            withdrawal     20.00          \nN.C            withdrawal     10.00          \nN.C            deposit        200.00         \nN.C            withdrawal     100.00         \nN.C            withdrawal     50.00          \n-----------------------------------\n"
        awaited_bank_statement = """\
Bank Statement for Dave Toe account:
-----------------------------------
Date           Operation      Amount         
-----------------------------------
N.C            deposit        100.00         
N.C            withdrawal     50.00          
N.C            withdrawal     20.00          
N.C            withdrawal     10.00          
N.C            deposit        200.00         
N.C            withdrawal     100.00         
N.C            withdrawal     50.00          
-----------------------------------"""
        #assert bank_statement == awaited_bank_statement, "bank statement should match the awaited one"

#####################
### Domain Model  ###
#####################

class Helper:
    @staticmethod
    def to_currency(amount: Union[str, float, Decimal]) -> Decimal:
        return Decimal(str(amount)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

class DomainModel:
    pass

class AggregateRoot(DomainModel):
    pass

class OperationType(Enum):
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    TRANSFER = "transfer"

#@dataclass(frozen=True) # Cannot be frozen because the init must be overridden
class Operation(DomainModel):
    operation_type: OperationType
    amount: Decimal
    
    def __init__(self, operation_type: OperationType, amount: Union[str, float, Decimal]):
        self.operation_type = operation_type
        self.amount = Helper.to_currency(amount)
    
    def __eq__(self, other):
        if not isinstance(other, Operation):
            return False
        return self.operation_type == other.operation_type and self.amount == other.amount
    
    def __repr__(self):
        return f"Operation({self.operation_type}, {self.amount})"

    @staticmethod
    def from_dict(data: dict) -> "Operation":
        return Operation(
                    operation_type=OperationType(data["operation_type"]),
                    amount=Helper.to_currency(data["amount"]))

class Account(DomainModel):
    def __init__(self, first_name: str, last_name: str, id: UUID = None):
        self.first_name: str = first_name
        self.last_name: str = last_name
        self.id: UUID = id if id else uuid.uuid4()
        self.operations: list[Operation] = []

    def __eq__(self, other):
        if not isinstance(other, Account):
            return False
        return self.id == other.id and self.first_name == other.first_name and self.last_name == other.last_name

    def __repr__(self):
        return f"BankModel({self.first_name}, {self.last_name})"
    
    def get_balance(self) -> Decimal:
        balance: Decimal = Helper.to_currency(0.0)
        for operation in self.operations:
            if operation.operation_type == OperationType.DEPOSIT:
                balance += operation.amount
            elif operation.operation_type == OperationType.WITHDRAWAL:
                balance -= operation.amount
            elif operation.operation_type == OperationType.TRANSFER:
                balance -= operation.amount
        return Helper.to_currency(balance)
    
    def deposit(self, amount: Decimal) -> Decimal:
        if amount <= 0:
            raise ValueError("Deposit amount must be positive")
        self.operations.append(Operation(OperationType.DEPOSIT, amount))
        return self.get_balance()
    
    def withdrawal(self, amount: Decimal) -> Decimal:
        amount = Helper.to_currency(amount)
        if amount <= 0:
            raise ValueError("Withdrawal amount must be positive")
        if amount > self.get_balance():
            raise ValueError("Insufficient funds")
        self.operations.append(Operation(OperationType.WITHDRAWAL, amount))
        return self.get_balance()
    
    def get_operations(self) -> list[Operation]:
        return self.operations.copy()
    
    def get_bank_statement(self) -> str:
        statement = f"Bank Statement for {self.first_name} {self.last_name} account:\n"
        statement += "-----------------------------------\n"
        statement += f"{'Date':<15}{'Operation':<15}{'Amount':<15}\n"
        statement += "-----------------------------------\n"
        for operation in self.operations:
            statement += f"{'N.C':<15}{operation.operation_type.value:<15}{operation.amount:<15}\n"
        return statement + "-----------------------------------\n"
    

class Bank(AggregateRoot):
    def __init__(self, name: str, accounts: list[Account] = None):
        self.name = name
        self._accounts = accounts if accounts else []

    def __eq__(self, other):
        if not isinstance(other, Bank):
            return False
        return self.name == other.name and self._accounts == other._accounts
    
    def get_all_accounts_ids(self) -> list[UUID]:
        return [acc.id for acc in self._accounts]
    
    def get_account_by_id(self, account_id: UUID) -> Account:
        account = next((acc for acc in self._accounts if acc.id == account_id), None)    
        if not account: raise ValueError("Account not found")
        return account
    
    def get_account_by_user_name(self, first_name: str, last_name: str) -> any:
        return next((acc for acc in self._accounts if acc.first_name == first_name and acc.last_name == last_name), None)
    
    def add_account(self, first_name: str, last_name: str) -> UUID:
        new_account = Account(first_name, last_name)
        self._accounts.append(new_account)
        return new_account.id
    
    def deposit_to_account(self, account_id: UUID, amount: Decimal) -> Decimal:
        account = self.get_account_by_id(account_id)
        return account.deposit(amount)
    
    def withdrawal_from_account(self, account_id: UUID, amount: Decimal) -> Decimal:
        account = self.get_account_by_id(account_id)
        return account.withdrawal(amount)
    
    def get_account_balance(self, account_id: UUID) -> Decimal:
        account = self.get_account_by_id(account_id)
        return account.get_balance()
    
    def get_account_operations(self, account_id: UUID) -> list[Operation]:
        account = self.get_account_by_id(account_id)
        return account.get_operations()

    def get_account_bank_statement(self, account_id: UUID) -> str:
        account = self.get_account_by_id(account_id)
        return account.get_bank_statement() 


###################
### Services    ###
###################

class BankingServices:
    def __init__(self):
        self._bank: Bank = Bank("My Bank")
    
    def create_account(self, first_name: str, last_name: str) -> UUID:
        new_account_id = self._bank.add_account(first_name= first_name, last_name= last_name)
        return new_account_id
    
    def get_all_accounts_ids(self) -> list[UUID]:
        return self._bank.get_all_accounts_ids()
    
    def get_account_by_id(self, account_id: UUID) -> Account:
        return self._bank.get_account_by_id(account_id)
    
    def get_account_by_user_name(self, first_name: str, last_name: str) -> Account:
        return self._bank.get_account_by_user_name(first_name, last_name)
    
    def deposit_to_account(self, account_id: UUID, amount: Decimal) -> Decimal:
        return self._bank.deposit_to_account(account_id, amount)
    
    def withdrawal_from_account(self, account_id: UUID, amount: Decimal) -> Decimal:
        return self._bank.withdrawal_from_account(account_id, amount)
        
    def get_account_balance(self, account_id: UUID) -> Decimal:
        return self._bank.get_account_balance(account_id)
        
    def get_account_operations(self, account_id: UUID) -> list[Operation]:
        return self._bank.get_account_operations(account_id)
    
    def get_account_bank_statement(self, account_id: UUID) -> str:
        return self._bank.get_account_bank_statement(account_id)

