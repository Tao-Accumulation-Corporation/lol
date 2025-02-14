import time
import torch
import argparse
import bittensor as bt

def get_stake_balances(subtensor, metagraph):
    balances = {}
    for uid in range(len(metagraph.hotkeys)):
        hotkey = metagraph.hotkeys[uid]
        neuron_info = subtensor.get_neuron_for_pubkey_and_subnet(
            hotkey_ss58=hotkey,
            netuid=metagraph.netuid
        )
        if neuron_info and not neuron_info.is_null:
            alpha_stake = float(neuron_info.stake.tao)
            balances[uid] = alpha_stake
        else:
            balances[uid] = 0.0
    return balances

def normalize_weights(balances, total_uids):
    weights = torch.zeros(total_uids)
    balance_items = sorted(balances.items(), key=lambda x: x[1], reverse=True)
    print("\nApplying multipliers")
    for idx, (uid, balance) in enumerate(balance_items):
        if balance > 0:
            if idx == 0:  # Top position gets 2x multiplier
                weights[uid] = balance * 2.0
                print(f"UID {uid}: Original stake: {balance}, After 2.0x multiplier: {balance * 2.0}") # whoa momma
            elif idx < 5:  # Positions 2-5 get 1.5x multiplier
                weights[uid] = balance * 1.5
                print(f"UID {uid}: Original stake: {balance}, After 1.5x multiplier: {balance * 1.5}") # skibbity toilet
            else:
                weights[uid] = balance
    weights = weights + 1e-10
    weights = weights / weights.sum()
    print("\nFinal normalized weights for top 10:")
    sorted_weights = sorted([(i, w.item()) for i, w in enumerate(weights)], key=lambda x: x[1], reverse=True)
    # for i, (uid, weight) in enumerate(sorted_weights[:10]):
        # print(f"UID {uid}: {weight:.6f}")
    return weights

def set_weights(wallet, subtensor, metagraph, config, balances):
    try:
        # Filter out UIDs that are receiving dividends. Validators have no place here
        non_dividend_uids = [uid for uid, dividend in enumerate(metagraph.dividends) if dividend == 0]
        print(f"\nUIDs not receiving dividends: {non_dividend_uids}")

        # Remove UIDs receiving dividends from balances
        filtered_balances = {uid: balance for uid, balance in balances.items() if uid in non_dividend_uids}

        # Normalize weights with the total number of UIDs
        weights = normalize_weights(filtered_balances, len(metagraph.uids))
        print(weights)

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
        print(f"uh oh oh uh wope3nrg error: {e}")
        return False

def main():
    parser = argparse.ArgumentParser()
    bt.wallet.add_args(parser)
    bt.subtensor.add_args(parser)
    bt.logging.add_args(parser)
    parser.add_argument('--netuid', type=int, default=28)
    config = bt.config(parser)
    wallet = bt.wallet(config=config)
    subtensor = bt.subtensor(config=config)
    print("Checking metagraph")
    metagraph = subtensor.metagraph(config.netuid)
    print(f"Metagraph: {metagraph}")
    while True:
        try:
            metagraph.sync()
            print(f"Running validator on subnet {config.netuid}")
            balances = get_stake_balances(subtensor, metagraph)
            print(balances)
            set_weights(wallet, subtensor, metagraph, config, balances)
            print("sleepy time. back in 20")
            time.sleep(1200)
        except Exception as e:
            print(f"uh oh shit uhhhh ewropginweropgin error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
