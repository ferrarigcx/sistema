const path = require('path');
const fs = require('fs-extra');
var ethers = require('ethers');

// RPCNODE details
const { besu } = require("../keys.js");
const host = besu.rpcnode.url;
const accountPrivateKey = besu.rpcnode.accountPrivateKey;

// abi and bytecode generated from simplestorage.sol:
// > solcjs --bin --abi simplestorage.sol
const contractJsonPath = path.resolve(__dirname, '../../', 'contracts', 'HashStorage.json');
const contractJson = JSON.parse(fs.readFileSync(contractJsonPath));
const contractAbi = contractJson.abi;
const contractBytecode = contractJson.evm.bytecode.object

async function main() {
    const provider = new ethers.JsonRpcProvider(host);
    const wallet = new ethers.Wallet(accountPrivateKey, provider);
     const args = process.argv.slice(2);

    //const adress = process.argv.slice(2);

    //adress = endereço
    //contractabi = funções 
    //provider = url do site
    const readOnlyContract = new ethers.Contract(args[1], contractAbi, provider);
    //const writableContract = readOnlyContract.connect(wallet);
    // Get events from block 0 to latest



    const latestBlock = await provider.getBlockNumber();
    const step = 5000; // chunk size
    let fromBlock = 0;
    let toBlock = step;


    while (fromBlock <= latestBlock) {


        if (toBlock > latestBlock) {
            toBlock = latestBlock;
        }
        const contracts = await readOnlyContract.queryFilter("video", fromBlock, toBlock);

       // console.log(contracts)
        for (const contract of contracts) {
            
         
             if (contract.args.storedHash == args[0]) {
                console.log(args[0])
                return args[0];
            }
        }

        // Move to the next block range
        fromBlock = toBlock + 1;
        toBlock = fromBlock + step;



    }
    return '';

}

if (require.main === module) {
    main();
}

module.exports = exports = main