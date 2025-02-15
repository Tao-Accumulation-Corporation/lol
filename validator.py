import time
import torch
import argparse
import bittensor as bt

def get_coldkey_balances(subtensor, netuid):
    """
    Need to use coldkey because hotkeys always return the balance that is staked TO them.
    Sorry bros. Wasnt clear in docs. Hopefully theres an update later. Blame the intern.
    """
    balances = {}
    used_coldkeys = set()

    try:
        # get neurons
        neurons = subtensor.neurons(netuid=netuid)

        # fetch coldkey balance. set to 0 if its already been done. 1 UID per coldkey.
        for uid, neuron in enumerate(neurons):
            if neuron.coldkey in used_coldkeys:
                # already accounted for this coldkey's stake; subsequent UIDs get 0
                balances[uid] = 0.0
                continue

            # get coldkey stake
            try:
                stake_infos = subtensor.get_stake_for_coldkey(coldkey_ss58=neuron.coldkey)
            except Exception as e:
                print(f"Error retrieving stake for coldkey {neuron.coldkey}: {e}")
                balances[uid] = 0.0
                continue

            total_stake_for_coldkey = 0.0
            for stake_info in stake_infos:
                if stake_info.netuid == netuid:
                    total_stake_for_coldkey += float(stake_info.stake)

            balances[uid] = total_stake_for_coldkey

            # this coldkey has been used and abused
            used_coldkeys.add(neuron.coldkey)

        # print final coldkey-based balances
        print("\nFinal coldkey-based balances by UID:")
        for uid, stake in sorted(balances.items()):
            print(
                f"UID {uid} (hotkey: {neurons[uid].hotkey}, "
                f"coldkey: {neurons[uid].coldkey}): {stake}"
            )

    except Exception as e:
        print(f"Error retrieving neurons for netuid={netuid}: {e}")

    return balances


def normalize_weights(balances, total_uids):
    weights = torch.zeros(total_uids)
    balance_items = sorted(balances.items(), key=lambda x: x[1], reverse=True)

    print("\nApplying multipliers")
    for idx, (uid, balance) in enumerate(balance_items):
        if balance > 0:
            if idx == 0:  # Top staker gets a 2.0x multiplier
                weights[uid] = balance * 2.0 # whoa momma
            elif idx < 5:  # Ranks 2-5 get 1.5x multiplier
                weights[uid] = balance * 1.5 # LFG
            else:
                weights[uid] = balance

    # we dont divide by zero here at TaoAccumulationCorporation
    weights = weights + 1e-10
    weights = weights / weights.sum()

    # Print the top-10 weights for debug
    print("\nFinal normalized weights for top 10:")
    sorted_weights = sorted(
        [(i, w.item()) for i, w in enumerate(weights)], key=lambda x: x[1], reverse=True
    )
    for i, (uid, weight) in enumerate(sorted_weights[:10]):
        print(f"UID {uid}: {weight:.6f}")

    return weights


def set_weights(wallet, subtensor, metagraph, config, balances):
    """
    validators can get fucked for all im concerned
    """
    try:
        non_dividend_uids = [
            uid for uid, dividend in enumerate(metagraph.dividends) if dividend == 0
        ]
        print(f"\nUIDs not receiving dividends: {non_dividend_uids}")

        # Filter out any UIDs that are receiving dividends from the final balances
        filtered_balances = {
            uid: balance
            for uid, balance in balances.items()
            if uid in non_dividend_uids
        }

        # Convert those filtered balances into normalized weights
        weights = normalize_weights(filtered_balances, len(metagraph.uids))
        print(weights)

        # set weights
        result = subtensor.set_weights(
            netuid=config.netuid,
            wallet=wallet,
            uids=metagraph.uids,
            weights=weights,
            wait_for_inclusion=True,
            wait_for_finalization=False,
        )
        print(result)

    except Exception as e:
        print(f"Error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    parser.add_argument("--netuid", type=int, default=28)

    # Parse and build the config
    config = bt.config(parser)

    # Initialize wallet and subtensor
    wallet = bt.wallet(config=config)
    subtensor = bt.subtensor(config=config)

    print("Checking metagraph")
    metagraph = subtensor.metagraph(config.netuid)
    print(f"Metagraph: {metagraph}")

    # Loop forever: sync metagraph, gather balances, set weights, sleep
    while True:
        try:
            metagraph.sync()
            print(f"Running validator on subnet {config.netuid}")

            # Gather total stake by coldkey and assign it to the first UID
            balances = get_coldkey_balances(subtensor, config.netuid)
            print(balances)

            # Set weights on-chain
            set_weights(wallet, subtensor, metagraph, config, balances)

            print("Sleeping for 20 minutes")
            time.sleep(1200)

        except Exception as e:
            print(f"Error in main loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
