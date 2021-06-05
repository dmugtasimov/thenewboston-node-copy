from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from thenewboston_node.business_logic.blockchain.mock_blockchain import MockBlockchain
from thenewboston_node.business_logic.models import (
    CoinTransferSignedChangeRequest, CoinTransferSignedChangeRequestMessage, CoinTransferTransaction
)
from thenewboston_node.business_logic.models.block import Block
from thenewboston_node.business_logic.node import get_node_signing_key
from thenewboston_node.core.utils.cryptography import KeyPair, derive_verify_key


@pytest.mark.usefixtures('get_next_block_identifier_mock', 'get_next_block_number_mock')
def test_can_create_block_from_signed_change_request(
    forced_mock_blockchain, sample_signed_change_request: CoinTransferSignedChangeRequest
):

    sender = sample_signed_change_request.signer
    assert sender

    def get_account_balance(self, account, on_block_number):
        return 450 if account == sender else 0

    with patch.object(MockBlockchain, 'get_account_balance', new=get_account_balance):
        block = Block.create_from_signed_change_request(forced_mock_blockchain, sample_signed_change_request)

    assert block.message
    assert block.message_hash
    assert block.signature
    block.validate_signature()
    assert block.signer
    assert block.signer == derive_verify_key(get_node_signing_key())

    block_message = block.message

    signed_change_request = block_message.signed_change_request
    assert signed_change_request == sample_signed_change_request
    assert signed_change_request is not sample_signed_change_request  # test that a copy of it was made

    assert isinstance(block_message.timestamp, datetime)
    assert block_message.timestamp.tzinfo is None
    assert block_message.timestamp - datetime.utcnow() < timedelta(seconds=1)

    assert block_message.block_number == 0
    assert block_message.block_identifier == 'next-block-identifier'
    updated_account_states = block_message.updated_account_states

    assert isinstance(updated_account_states, dict)
    assert len(updated_account_states) == 4

    assert updated_account_states[sender].balance == 450 - 425 - 4 - 1
    assert updated_account_states[sender].balance_lock

    assert updated_account_states['484b3176c63d5f37d808404af1a12c4b9649cd6f6769f35bdf5a816133623fbc'].balance == 425
    assert updated_account_states['484b3176c63d5f37d808404af1a12c4b9649cd6f6769f35bdf5a816133623fbc'
                                  ].balance_lock is None

    assert updated_account_states['ad1f8845c6a1abb6011a2a434a079a087c460657aad54329a84b406dce8bf314'].balance == 4
    assert updated_account_states['ad1f8845c6a1abb6011a2a434a079a087c460657aad54329a84b406dce8bf314'
                                  ].balance_lock is None

    assert updated_account_states['5e12967707909e62b2bb2036c209085a784fabbc3deccefee70052b6181c8ed8'].balance == 1
    assert updated_account_states['5e12967707909e62b2bb2036c209085a784fabbc3deccefee70052b6181c8ed8'
                                  ].balance_lock is None


@pytest.mark.usefixtures(
    'forced_mock_network', 'get_next_block_identifier_mock', 'get_next_block_number_mock', 'get_account_state_mock',
    'get_account_lock_mock', 'get_primary_validator_mock', 'get_preferred_node_mock'
)
def test_can_create_block_from_main_transaction(
    forced_mock_blockchain, treasury_account_key_pair: KeyPair, user_account_key_pair: KeyPair,
    primary_validator_key_pair: KeyPair, node_key_pair: KeyPair
):

    def get_account_balance(self, account, on_block_number):
        return 430 if account == treasury_account_key_pair.public else 0

    with patch.object(MockBlockchain, 'get_account_balance', new=get_account_balance):
        block = Block.from_main_transaction(
            forced_mock_blockchain, user_account_key_pair.public, 20, signing_key=treasury_account_key_pair.private
        )

    # Assert block
    assert block.message
    assert block.message_hash
    assert block.signature

    block.validate_signature()
    assert block.signer
    assert block.signer == derive_verify_key(get_node_signing_key())

    # Assert block.message
    block_message = block.message
    assert block_message
    assert isinstance(block_message.timestamp, datetime)
    assert block_message.timestamp.tzinfo is None
    assert block_message.timestamp - datetime.utcnow() < timedelta(seconds=1)

    assert block_message.block_number == 0
    assert block_message.block_identifier == 'next-block-identifier'
    updated_account_states = block_message.updated_account_states

    assert isinstance(updated_account_states, dict)
    assert len(updated_account_states) == 4

    assert updated_account_states[treasury_account_key_pair.public].balance == 430 - 25
    assert updated_account_states[treasury_account_key_pair.public].balance_lock

    assert updated_account_states[user_account_key_pair.public].balance == 20
    assert updated_account_states[user_account_key_pair.public].balance_lock is None

    assert updated_account_states[primary_validator_key_pair.public].balance == 4
    assert updated_account_states[primary_validator_key_pair.public].balance_lock is None

    assert updated_account_states[node_key_pair.public].balance == 1
    assert updated_account_states[node_key_pair.public].balance_lock is None

    # Assert block_message.signed_change_request
    signed_change_request = block_message.signed_change_request
    assert signed_change_request.signer == treasury_account_key_pair.public
    assert signed_change_request.signature

    # Assert block_message.signed_change_request.message
    coin_transfer_signed_request_message = signed_change_request.message
    assert isinstance(coin_transfer_signed_request_message, CoinTransferSignedChangeRequestMessage)
    assert coin_transfer_signed_request_message.balance_lock
    assert len(coin_transfer_signed_request_message.txs) == 3
    txs_dict = {tx.recipient: tx for tx in coin_transfer_signed_request_message.txs}
    assert len(txs_dict) == 3

    assert txs_dict[user_account_key_pair.public].amount == 20
    assert txs_dict[user_account_key_pair.public].fee is None

    assert txs_dict[primary_validator_key_pair.public].amount == 4
    assert txs_dict[primary_validator_key_pair.public].fee

    assert txs_dict[node_key_pair.public].amount == 1
    assert txs_dict[node_key_pair.public].fee

    assert coin_transfer_signed_request_message.get_total_amount() == 25


@pytest.mark.usefixtures('get_next_block_identifier_mock', 'get_next_block_number_mock', 'get_account_state_mock')
def test_normalized_block_message(forced_mock_blockchain, sample_signed_change_request):
    expected_message_template = (
        '{'
        '"block_identifier":"next-block-identifier",'
        '"block_number":0,'
        '"block_type":"ct",'
        '"signed_change_request":'
        '{"message":{"balance_lock":'
        '"4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732",'
        '"txs":'
        '[{"amount":425,"recipient":"484b3176c63d5f37d808404af1a12c4b9649cd6f6769f35bdf5a816133623fbc"},'
        '{"amount":1,"fee":true,"recipient":"5e12967707909e62b2bb2036c209085a784fabbc3deccefee70052b6181c8ed8"},'
        '{"amount":4,"fee":true,"recipient":'
        '"ad1f8845c6a1abb6011a2a434a079a087c460657aad54329a84b406dce8bf314"}]},'
        '"signature":"8c1b5719745cdc81e71905e874c1f1fb938d941dd6d03ddc6dc39fc60ca42dcb8a17bb2e721c3f2a'
        '128a2dff35a3b0f843efe78893adde78a27192ca54212a08",'
        '"signer":"4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732"},'
        '"timestamp":"<replace-with-timestamp>",'
        '"updated_account_states":{'
        '"484b3176c63d5f37d808404af1a12c4b9649cd6f6769f35bdf5a816133623fbc":{"balance":425},'
        '"4d3cf1d9e4547d324de2084b568f807ef12045075a7a01b8bec1e7f013fc3732":'
        '{'
        '"balance":20,'
        '"balance_lock":"ae4116766c916e761c5ab7590e2426f9c391078519d8cef8673ee3fe0cdb75ad"'
        '},'
        '"5e12967707909e62b2bb2036c209085a784fabbc3deccefee70052b6181c8ed8":{"balance":1},'
        '"ad1f8845c6a1abb6011a2a434a079a087c460657aad54329a84b406dce8bf314":{"balance":4}'
        '}'
        '}'
    )

    def get_account_balance(self, account, on_block_number):
        return 450 if account == sample_signed_change_request.signer else 0

    with patch.object(MockBlockchain, 'get_account_balance', new=get_account_balance):
        block = Block.create_from_signed_change_request(forced_mock_blockchain, sample_signed_change_request)

    expected_message = expected_message_template.replace(
        '<replace-with-timestamp>', block.message.timestamp.isoformat()
    ).encode('utf-8')
    assert block.message.get_normalized() == expected_message


@pytest.mark.usefixtures('get_next_block_identifier_mock', 'get_next_block_number_mock', 'get_account_state_mock')
def test_can_serialize_deserialize(forced_mock_blockchain, sample_signed_change_request):
    block = Block.create_from_signed_change_request(forced_mock_blockchain, sample_signed_change_request)
    serialized_dict = block.to_dict()
    deserialized_block = Block.from_dict(serialized_dict)
    assert deserialized_block == block
    assert deserialized_block is not block


@pytest.mark.usefixtures('get_next_block_identifier_mock', 'get_next_block_number_mock', 'get_account_lock_mock')
def test_can_duplicate_recipients(
    forced_mock_blockchain: MockBlockchain, treasury_account_key_pair: KeyPair, user_account_key_pair: KeyPair
):

    def get_account_balance(self, account, on_block_number):
        return 430 if account == treasury_account_key_pair.public else 10

    sender = treasury_account_key_pair.public
    recipient = user_account_key_pair.public
    message = CoinTransferSignedChangeRequestMessage(
        balance_lock=forced_mock_blockchain.get_account_balance_lock(sender),
        txs=[
            CoinTransferTransaction(recipient=recipient, amount=3),
            CoinTransferTransaction(recipient=recipient, amount=5),
        ]
    )
    request = CoinTransferSignedChangeRequest.create_from_signed_change_request_message(
        message, treasury_account_key_pair.private
    )

    with patch.object(MockBlockchain, 'get_account_balance', new=get_account_balance):
        block = Block.create_from_signed_change_request(forced_mock_blockchain, request)

    updated_account_states = block.message.updated_account_states
    assert len(updated_account_states) == 2

    sender_account_state = block.message.get_account_state(treasury_account_key_pair.public)
    assert sender_account_state
    assert sender_account_state.balance == 430 - 3 - 5
    assert sender_account_state.balance_lock

    recipient_account_state = block.message.get_account_state(user_account_key_pair.public)
    assert recipient_account_state
    assert recipient_account_state.balance == 10 + 3 + 5


@pytest.mark.skip('Not implemented yet')
def test_validate_block():
    raise NotImplementedError()